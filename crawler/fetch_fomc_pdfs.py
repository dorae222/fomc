#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOMC PDF Collector (Fixed v3)
- Correctly separates 'Longer-Run Goals' as framework (not meeting statements)
- Stronger discovery for statements/minutes PDFs under /newsevents/pressreleases/monetary and /monetarypolicy/files/
- Keeps strict PDF-only behavior by default; optional --include-html-fallback saves HTML when no PDF (for statements)
- Strict date parsing, transcript 5y lag, future-date block, SHA1 dedup, resume, concurrency, summary

Usage (PDF만):
  python fetch_fomc_pdfs_fixed.py --out data/raw \
    --index-url "https://www.federalreserve.gov/monetarypolicy/fomc_historical_year.htm" \
    --types statement minutes beigebook transcript tealbook framework \
    --years 1990-2025 \
    --max-workers 10 --delay 0.25 --resume \
    --strict-content-type --validate-header \
    --min-size 8000 --max-size 200000000

HTML fallback 포함(성명문 HTML도 저장):
  python fetch_fomc_pdfs_fixed_v3.py ... --include-html-fallback
"""
from __future__ import annotations

import argparse, csv, hashlib, json, logging, math, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# -----------------------------
# Config
# -----------------------------
DEFAULT_INDEX_URL = "https://www.federalreserve.gov/monetarypolicy/fomc_historical_year.htm"
DEFAULT_UA = "Mozilla/5.0 (compatible; FOMC-PDF-Collector/FixedV3/1.0; +contact@example.com)"

# 유형 정의
DOC_TYPE_KEYWORDS = {
    "statement":  ["statement", "fomcstatement", "/fomcstatements/", "pressreleases/monetary"],
    "minutes":    ["minutes", "/fomcminutes/"],
    "beigebook":  ["beige book", "beigebook", "beige-book"],
    "transcript": ["transcript"],
    "tealbook":   ["tealbook", "greenbook"],
    # 새로 추가: 정책 프레임워크(연 1회) 분리
    "framework":  ["longer run goals", "longer-run goals", "fomc_longerrungoals", "longerrungoals"],
}

# Allowlist paths
TYPE_ALLOWLIST = {
    "statement":  ["/newsevents/pressreleases/monetary", "/monetarypolicy/files/", "/monetarypolicy/fomcstatements"],
    "minutes":    ["/monetarypolicy/fomcminutes", "/monetarypolicy/files/"],
    "beigebook":  ["/monetarypolicy/beigebook"],
    "transcript": ["/monetarypolicy/"],
    "tealbook":   ["/monetarypolicy/"],
    "framework":  ["/monetarypolicy/files/"],
}

PDF_RE   = re.compile(r"\.pdf(\?.*)?$", re.IGNORECASE)
YEAR_RE  = re.compile(r"(19|20)\d{2}")
DATE_YYYYMMDD = re.compile(r"(19|20)\d{2}[01]\d[0-3]\d")

# 파일명·URL 휴리스틱 강화
RE_STMT_FILE = re.compile(r"(/files/.*(statement|monetary).*\.(pdf|htm|html)|pressreleases/monetary)", re.IGNORECASE)
RE_MIN_FILE  = re.compile(r"(/fomcminutes/|/files/.*minutes.*\.(pdf|htm|html))", re.IGNORECASE)
RE_FRAMEWORK = re.compile(r"(longerrungoals|longer[-_ ]run[-_ ]goals)", re.IGNORECASE)

MONTHS = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,"may":5,
    "jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,"sept":9,"september":9,
    "oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12
}
TODAY = date.today()

# -----------------------------
# Data classes
# -----------------------------
@dataclass
class DocLink:
    url: str
    text: str
    context_url: str
    doc_type: Optional[str] = None
    date: Optional[datetime] = None
    year_hint: Optional[int] = None
    is_html_fallback: bool = False  # HTML 저장 여부 표시

@dataclass
class ManifestRow:
    saved_path: str
    doc_type: str
    year: int
    meeting_id: str
    source_url: str
    context_url: str
    link_text: str
    title_guess: str
    date_guess: str
    sha1: str
    size: int

# -----------------------------
# HTTP session
# -----------------------------
def requests_session(user_agent: str, pool: int = 64) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    retries = Retry(total=6, backoff_factor=0.7,
                    status_forcelist=[429,500,502,503,504],
                    allowed_methods=["GET","HEAD"], raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retries, pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", adapter); s.mount("http://", adapter)
    return s

def http_get(s: requests.Session, url: str, timeout: int = 45) -> Optional[requests.Response]:
    try:
        r = s.get(url, timeout=timeout, allow_redirects=True)
        if r.ok: return r
        return None
    except Exception:
        return None

def http_head(s: requests.Session, url: str, timeout: int = 20) -> Optional[requests.Response]:
    try:
        r = s.head(url, timeout=timeout, allow_redirects=True)
        if r.ok: return r
        return None
    except Exception:
        return None

# -----------------------------
# Utils
# -----------------------------
def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-\.]", "_", name)

def is_pdf_url(url: str) -> bool:
    return bool(PDF_RE.search(url))

def content_type_is_pdf(session: requests.Session, url: str) -> bool:
    r = http_head(session, url)
    if not r: return False
    ct = (r.headers.get("Content-Type") or "").lower()
    return "application/pdf" in ct

def pdf_magic_ok(buf: bytes) -> bool:
    return buf.startswith(b"%PDF")

def sha1_bytes(b: bytes) -> str:
    h = hashlib.sha1(); h.update(b); return h.hexdigest()

def guess_doc_type(text: str, url: str) -> Optional[str]:
    s = (text or "").lower() + " " + (url or "").lower()
    if RE_FRAMEWORK.search(s): return "framework"
    if "transcript" in s: return "transcript"
    if "beige book" in s or "beigebook" in s or "beige-book" in s: return "beigebook"
    if "tealbook" in s or "greenbook" in s: return "tealbook"
    if "minutes" in s or "/fomcminutes/" in s or RE_MIN_FILE.search(s): return "minutes"
    if "statement" in s or "/fomcstatements/" in s or "pressreleases/monetary" in s or RE_STMT_FILE.search(s): return "statement"
    return None

def url_allowed_for_type(url: str, dtype: str) -> bool:
    url_l = url.lower()
    allow = TYPE_ALLOWLIST.get(dtype, [])
    return any(p in url_l for p in allow) if allow else True

def parse_date_strict(url: str, text: str) -> Optional[datetime]:
    s = f"{url} {text}"
    m = DATE_YYYYMMDD.search(s)
    if m:
        ds = m.group(0); y, mn, dy = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
        try: return datetime(y, mn, dy)
        except ValueError: pass
    m2 = re.search(r"(?P<mon>[A-Za-z]{3,9})\s+(?P<day>[12]?\d|3[01])\,?\s+(?P<yr>(19|20)\d{2})", s, re.I)
    if m2:
        mon = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}.get(m2.group("mon").lower()[:3])
        if mon:
            try: return datetime(int(m2.group("yr")), mon, int(m2.group("day")))
            except ValueError: pass
    m3 = re.search(r"(?P<day>[12]?\d|3[01])\s+(?P<mon>[A-Za-z]{3,9})\s+(?P<yr>(19|20)\d{2})", s, re.I)
    if m3:
        mon = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}.get(m3.group("mon").lower()[:3])
        if mon:
            try: return datetime(int(m3.group("yr")), mon, int(m3.group("day")))
            except ValueError: pass
    return None

def parse_date_any_loose(text: str) -> Optional[datetime]:
    t = normalize_space(text)
    try:
        dt = dateparser.parse(t, fuzzy=True)
        if dt and 1950 <= dt.year <= 2100:
            return dt
    except Exception:
        pass
    m = YEAR_RE.search(t)
    if m:
        try: return datetime(int(m.group(0)), 1, 1)
        except Exception: pass
    return None

def build_meeting_id(dt: Optional[datetime], doc_type: Optional[str], url: str, fallback_text: str) -> Tuple[str, int]:
    if dt:
        ymd = dt.strftime("%Y%m%d"); dtype = doc_type or "document"
        return f"{ymd}_{dtype}", dt.year
    m = YEAR_RE.search(url) or YEAR_RE.search(fallback_text or "")
    year = int(m.group(0)) if m else 1900
    h = hashlib.sha1(url.encode()).hexdigest()[:8]
    dtype = doc_type or "document"
    return f"{year}xxxxxx_{dtype}_{h}", year

def transcript_allowed_by_lag(d: Optional[datetime], lag_years: int = 5) -> bool:
    if not d: return True
    return (TODAY.year - d.year) >= lag_years

def future_date_blocked(d: Optional[datetime]) -> bool:
    return bool(d and d.date() > TODAY)

# -----------------------------
# Crawl helpers
# -----------------------------
def parse_year_pages(session: requests.Session, index_url: str) -> List[str]:
    r = http_get(session, index_url)
    if not r: raise RuntimeError("Failed to load index page.")
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if "fomchistorical" in href and href.lower().endswith(".htm"):
            urls.append(urljoin(index_url, href))
    return sorted(set(urls))

def collect_links_from_page(session: requests.Session, url: str, include_html_fallback: bool) -> List[DocLink]:
    r = http_get(session, url)
    if not r: return []
    soup = BeautifulSoup(r.text, "html.parser")
    links: List[DocLink] = []
    for a in soup.select("a[href]"):
        href = urljoin(url, a["href"]); text = normalize_space(a.get_text(" "))
        low = href.lower()
        # 1) PDF 직접
        if is_pdf_url(low):
            links.append(DocLink(url=href, text=text, context_url=url))
        else:
            # 2) 중간 HTML 후보 (statement/minutes/beige/transcript/tealbook/pressreleases)
            if any(k in low for k in ["statement","minutes","beige","transcript","tealbook","greenbook","pressreleases","files"]):
                if include_html_fallback and ("pressreleases/monetary" in low or "/fomcminutes/" in low or "/fomcstatements" in low or "/monetarypolicy/files/" in low):
                    # HTML도 후보로 수집 (나중에 내부 PDF 추출; 없으면 HTML 저장)
                    links.append(DocLink(url=href, text=text, context_url=url, is_html_fallback=True))
                else:
                    links.append(DocLink(url=href, text=text, context_url=url))
    return links

def extract_pdfs_from_html(session: requests.Session, html_url: str) -> List[DocLink]:
    r = http_get(session, html_url)
    if not r: return []
    soup = BeautifulSoup(r.text, "html.parser")
    out: List[DocLink] = []
    for a in soup.select("a[href$='.pdf'], a[href*='.pdf?']"):
        pdf_url = urljoin(html_url, a["href"])
        out.append(DocLink(url=pdf_url, text=normalize_space(a.get_text(" ")), context_url=html_url))
    return out

# -----------------------------
# Manifest helpers
# -----------------------------
def write_manifest_header_if_needed(csv_path: str, jsonl_path: str):
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "saved_path","doc_type","year","meeting_id",
                "source_url","context_url","link_text",
                "title_guess","date_guess","sha1","size"
            ])
    if not os.path.exists(jsonl_path):
        with open(jsonl_path, "w", encoding="utf-8") as f:
            pass

def load_manifest_urls(csv_path: str) -> Set[str]:
    seen = set()
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                src = row.get("source_url","")
                if src: seen.add(src)
    return seen

def record_manifest(csv_path: str, jsonl_path: str, row: ManifestRow):
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            row.saved_path, row.doc_type, row.year, row.meeting_id,
            row.source_url, row.context_url, row.link_text,
            row.title_guess, row.date_guess, row.sha1, row.size
        ])
    with open(jsonl_path, "a", encoding="utf-8") as jf:
        jf.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

# -----------------------------
# Filters / args
# -----------------------------
def parse_years_arg(years: Optional[str]) -> Optional[Set[int]]:
    if not years: return None
    out: Set[int] = set()
    parts = [p.strip() for p in years.split(",")]
    for p in parts:
        if "-" in p:
            a, b = p.split("-", 1); a, b = int(a), int(b)
            for y in range(min(a,b), max(a,b)+1):
                out.add(y)
        else:
            out.add(int(p))
    return out

def parse_types_arg(types: Optional[List[str]]) -> Optional[Set[str]]:
    if not types: return None
    return set(t.strip().lower() for t in types)

def keep_by_filters(dtype: str, year: int,
                    allowed_types: Optional[Set[str]],
                    allowed_years: Optional[Set[int]]) -> bool:
    if allowed_types and dtype not in allowed_types: return False
    if allowed_years and year not in allowed_years: return False
    return True

# -----------------------------
# Download worker
# -----------------------------
def download_worker(
    session: requests.Session,
    out_dir: str,
    doc: DocLink,
    allowed_types: Optional[Set[str]],
    allowed_years: Optional[Set[int]],
    delay: float,
    strict_content_type: bool,
    validate_header: bool,
    min_size: int,
    max_size: int,
    seen_hashes: Set[str],
    include_html_fallback: bool,
) -> Tuple[str, Optional[ManifestRow], Optional[str]]:
    try:
        dtype = guess_doc_type(doc.text, doc.url) or doc.doc_type
        # extra overrides
        s = (doc.text + " " + doc.url).lower()
        if dtype is None:
            if RE_FRAMEWORK.search(s): dtype = "framework"
            elif RE_MIN_FILE.search(s): dtype = "minutes"
            elif RE_STMT_FILE.search(s): dtype = "statement"
        if dtype is None:
            return (doc.url, None, "unknown_type")

        if not url_allowed_for_type(doc.url, dtype):
            return (doc.url, None, "not_in_allowlist")

        # Parse date (strict first)
        dt = parse_date_strict(doc.url, doc.text) or parse_date_any_loose(doc.text) or parse_date_any_loose(doc.url)

        # Transcript 5y lag
        if dtype == "transcript" and dt and not transcript_allowed_by_lag(dt, 5):
            return (doc.url, None, "transcript_too_recent")

        # Future date block
        if dt and future_date_blocked(dt):
            return (doc.url, None, "future_date_blocked")

        meeting_id, year = build_meeting_id(dt, dtype, doc.url, doc.text)
        if not keep_by_filters(dtype, year, allowed_types, allowed_years):
            return (doc.url, None, "filtered")

        # ---- PDF path ----
        if is_pdf_url(doc.url):
            if strict_content_type and not content_type_is_pdf(session, doc.url):
                return (doc.url, None, "content_type_not_pdf")
            r = http_get(session, doc.url, timeout=90)
            if not r: return (doc.url, None, "download_failed")
            content = r.content
            if validate_header and not pdf_magic_ok(content[:5]):
                return (doc.url, None, "invalid_pdf_header")
            size = len(content)
            if min_size and size < min_size: return (doc.url, None, f"too_small({size})")
            if max_size and size > max_size: return (doc.url, None, f"too_large({size})")
            file_sha1 = sha1_bytes(content)
            if file_sha1 in seen_hashes: return (doc.url, None, "dup_sha1")
            seen_hashes.add(file_sha1)

            subdir = os.path.join(out_dir, dtype, str(year)); ensure_dir(subdir)
            fname = safe_filename(meeting_id + ".pdf"); fpath = os.path.join(subdir, fname)
            if not os.path.exists(fpath):
                with open(fpath, "wb") as f: f.write(content)
                if delay > 0: time.sleep(delay)

            row = ManifestRow(
                saved_path=os.path.relpath(fpath, out_dir),
                doc_type=dtype, year=year, meeting_id=meeting_id,
                source_url=doc.url, context_url=doc.context_url, link_text=doc.text,
                title_guess="", date_guess=dt.isoformat() if dt else "",
                sha1=file_sha1, size=size
            )
            return (doc.url, row, None)

        # ---- HTML path (optional fallback, 주로 statement 보도자료) ----
        if include_html_fallback and dtype in {"statement","minutes"} and doc.is_html_fallback:
            # 1) HTML에서 다시 PDF가 있으면 PDF 저장
            pdfs = extract_pdfs_from_html(session, doc.url)
            if pdfs:
                # pick first PDF (보통 1개)
                pdf_doc = pdfs[0]
                pdf_doc.text = doc.text
                pdf_doc.context_url = doc.url
                # 재귀적으로 PDF 경로 태워 저장
                pdf_doc.doc_type = dtype
                pdf_doc.date = dt
                pdf_doc.year_hint = year
                pdf_doc.is_html_fallback = False
                return download_worker(session, out_dir, pdf_doc, allowed_types, allowed_years,
                                       delay, strict_content_type, validate_header,
                                       min_size, max_size, seen_hashes, include_html_fallback)
            # 2) PDF가 없으면 HTML 자체를 저장(.html) (텍스트 추출 파이프라인에서 처리 가능)
            r = http_get(session, doc.url, timeout=60)
            if not r: return (doc.url, None, "download_failed_html")
            content = r.content
            size = len(content)
            # HTML 저장
            subdir = os.path.join(out_dir, dtype, str(year)); ensure_dir(subdir)
            fname = safe_filename(meeting_id + ".html"); fpath = os.path.join(subdir, fname)
            if not os.path.exists(fpath):
                with open(fpath, "wb") as f: f.write(content)
                if delay > 0: time.sleep(delay)
            file_sha1 = sha1_bytes(content)
            if file_sha1 in seen_hashes: return (doc.url, None, "dup_sha1")
            seen_hashes.add(file_sha1)
            row = ManifestRow(
                saved_path=os.path.relpath(fpath, out_dir),
                doc_type=dtype, year=year, meeting_id=meeting_id,
                source_url=doc.url, context_url=doc.context_url, link_text=doc.text,
                title_guess="", date_guess=dt.isoformat() if dt else "",
                sha1=file_sha1, size=size
            )
            return (doc.url, row, None)

        return (doc.url, None, "not_pdf_and_no_fallback")

    except Exception as e:
        return (doc.url, None, f"exception:{e}")

# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Strict FOMC Collector (Fixed v3).")
    ap.add_argument("--out", default="data/raw", help="Output base directory")
    ap.add_argument("--index-url", default=DEFAULT_INDEX_URL, help="Historical index URL")
    ap.add_argument("--years", default=None, help="Year filter, e.g., 1990-2025 or 2010,2012,2015")
    ap.add_argument("--types", nargs="*", default=None, help="Type filter: statement minutes beigebook transcript tealbook framework")
    ap.add_argument("--max-workers", type=int, default=10, help="Concurrent downloads")
    ap.add_argument("--delay", type=float, default=0.25, help="Delay between downloads (seconds)")
    ap.add_argument("--resume", action="store_true", help="Skip URLs already in manifest.csv")
    ap.add_argument("--strict-content-type", action="store_true", help="Require HEAD Content-Type application/pdf")
    ap.add_argument("--validate-header", action="store_true", help="Require %PDF header in file")
    ap.add_argument("--min-size", type=int, default=8000, help="Minimum bytes to accept (PDF)")
    ap.add_argument("--max-size", type=int, default=200_000_000, help="Maximum bytes to accept (PDF)")
    ap.add_argument("--include-html-fallback", action="store_true", help="If no PDF, save HTML for statements/minutes")
    ap.add_argument("--user-agent", default=DEFAULT_UA, help="Custom User-Agent")
    ap.add_argument("--log", default="INFO", help="Log level (DEBUG,INFO,WARNING,ERROR)")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(args, "log", "INFO"), format="%(asctime)s | %(levelname)s | %(message)s")

    out_dir = args.out; os.makedirs(out_dir, exist_ok=True)
    manifest_csv  = os.path.join(out_dir, "manifest.csv")
    manifest_json = os.path.join(out_dir, "manifest.jsonl")
    write_manifest_header_if_needed(manifest_csv, manifest_json)

    allowed_years = parse_years_arg(args.years)
    allowed_types = parse_types_arg(args.types)

    sess = requests_session(args.user_agent)

    # 1) Index -> year pages
    year_pages = parse_year_pages(sess, args.index_url)

    # 2) Collect candidates
    candidates: List[DocLink] = []
    for yp in tqdm(year_pages, desc="Collecting links from year pages"):
        candidates.extend(collect_links_from_page(sess, yp, include_html_fallback=args.include_html_fallback))

    # 3) Expand HTMLs to PDFs
    expanded: List[DocLink] = []
    for l in tqdm(candidates, desc="Expanding HTML to PDFs"):
        if is_pdf_url(l.url):
            expanded.append(l)
        else:
            expanded.extend(extract_pdfs_from_html(sess, l.url) if not l.is_html_fallback else [l])

    # 4) Unique by URL
    url2doc: Dict[str, DocLink] = {}
    for d in expanded:
        if d.url not in url2doc:
            url2doc[d.url] = d

    urls = list(url2doc.keys())

    # 5) Resume
    if args.resume:
        seen = load_manifest_urls(manifest_csv)
        before = len(urls)
        urls = [u for u in urls if u not in seen]
        logging.info(f"Resume: skipped {before-len(urls)} already-seen URLs; remaining {len(urls)}")
    logging.info(f"Unique candidates: {len(urls)}")

    # 6) Concurrent downloads
    success = skipped = failed = 0
    total_bytes = 0
    failures: List[Tuple[str, str]] = []
    seen_hashes: Set[str] = set()

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
        futures = {}
        for u in urls:
            doc = url2doc[u]
            fut = ex.submit(
                download_worker, sess, out_dir, doc,
                allowed_types, allowed_years,
                args.delay, args.strict_content_type, args.validate_header,
                args.min_size, args.max_size,
                seen_hashes, args.include_html_fallback
            )
            futures[fut] = doc
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Downloading"):
            src, row, err = fut.result()
            if row:
                record_manifest(manifest_csv, manifest_json, row)
                success += 1; total_bytes += row.size
            else:
                if err in {"filtered","unknown_type","not_pdf_ext","not_in_allowlist",
                           "transcript_too_recent","future_date_blocked","dup_sha1",
                           "content_type_not_pdf","not_pdf_and_no_fallback"} or (err and err.startswith("too_")):
                    skipped += 1
                else:
                    failed += 1; failures.append((src, err or "unknown"))

    # 7) Summary
    def bytes_to_h(n: int) -> str:
        units = ["B","KB","MB","GB"]
        if n <= 0: return "0 B"
        i = min(int(math.log(n, 1024)), len(units)-1)
        return f"{n/(1024**i):.2f} {units[i]}"

    logging.info("="*67)
    logging.info("FOMC Collection Summary (Fixed v3)")
    logging.info(f"Saved:   {success}")
    logging.info(f"Skipped: {skipped}")
    logging.info(f"Failed:  {failed}")
    logging.info(f"Size:    {bytes_to_h(total_bytes)}")
    if failures:
        logging.info("- Failures (up to 20) -")
        for u, e in failures[:20]:
            logging.info(f"{e:>24} | {u}")
    logging.info("Done.")

if __name__ == "__main__":
    main()
