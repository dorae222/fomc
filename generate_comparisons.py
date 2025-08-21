#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_comparisons_using_pred_probs.py

- Uses pred CSV fields (pred_label, max_prob) to compute hawk-share.
- Uses header-aware extraction of close prices from 1h CSVs (prefer 'close'/'adjclose' columns).
- Annotates plots (bottom band + slanted line) according to rules:
    * press > stmt AND last_close < prev_close  -> GREEN
    * press < stmt AND last_close > prev_close  -> GREEN
    * otherwise -> RED
- Skips pages if no matching 1h CSV exists.
- Deduplicates predicted files by date, prefers dedicated dirs over txt_pred.
"""
import os, re, glob, shutil, csv, math, datetime
from collections import OrderedDict
import numpy as np

# ---------- CONFIG ----------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PRED_DIR = os.path.join(PROJECT_ROOT, "predicted", "txt_pred")
PRED_STATEMENT_DIR = os.path.join(PROJECT_ROOT, "predicted", "statement_txt")
PRED_BLOCKS_PRES_DIR = os.path.join(PROJECT_ROOT, "predicted", "blocks_pres_txt")
PRED_CSV_DIR = os.path.join(PROJECT_ROOT, "predicted", "csv")
RESULTS_PLOTS_DIR = os.path.join(PROJECT_ROOT, "results", "plots")
RESULTS_CSV_DIR = os.path.join(PROJECT_ROOT, "results", "csv")
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
COMPARISONS_DIR = os.path.join(WEB_DIR, "comparisons")
PRES_PAGES_DIR = os.path.join(WEB_DIR, "pres")
PLOTS_WEB_DIR = os.path.join(WEB_DIR, "plots")
STYLE_PATH = os.path.join(WEB_DIR, "style.css")

os.makedirs(COMPARISONS_DIR, exist_ok=True)
os.makedirs(PRES_PAGES_DIR, exist_ok=True)
os.makedirs(PLOTS_WEB_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)

# Stats
PLOT_ANNOTATION_STATS = {"total": 0, "green": 0, "red": 0, "skipped": 0}
PLOT_ANNOTATED = set()

# Prob column candidates
PROB_COL_CANDIDATES = ["max_prob", "prob", "probability", "score", "confidence", "maxprob", "pred_prob"]
# ---------------- utilities ----------------
def escape_html(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&#39;"))

def ensure_style_css(path):
    if os.path.exists(path):
        return
    css = "body{font-family:Arial,Helvetica,sans-serif;margin:20px}h1{font-size:1.2rem}.sent-text{padding:6px;border-radius:4px;display:block;margin:6px 0}"
    with open(path,"w",encoding="utf-8") as f:
        f.write(css)

# ---------------- read prediction CSV (existing logic) ----------------
def find_prob_column_index(headers):
    norm = [h.strip().lower() for h in headers]
    for cand in PROB_COL_CANDIDATES:
        if cand in norm:
            return norm.index(cand)
    for i, h in enumerate(norm):
        for cand in PROB_COL_CANDIDATES:
            if cand in h:
                return i
    return None

def read_pred_csv(filepath):
    """
    Returns list of {"pred_label","text","max_prob"} robustly.
    This is the canonical reader used for pages and hawk-share calc.
    """
    results = []
    if not os.path.isfile(filepath):
        return results
    try:
        with open(filepath, "r", encoding="utf-8", newline='') as f:
            sample = f.read(8192); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            headers = []
            try:
                headers = next(reader)
            except StopIteration:
                headers = []
            norm_headers = [h.strip().lower() for h in headers]
            def find_any(cands):
                for c in cands:
                    if c in norm_headers:
                        return norm_headers.index(c)
                return None
            idx_pred = find_any(["pred_label","predlabel","pred","label"])
            idx_text = find_any(["text","content","sentence","body"])
            idx_prob = find_prob_column_index(headers or [])
            if idx_text is None:
                idx_text = len(headers)-1 if headers else 0
            if idx_pred is None:
                idx_pred = 1 if len(headers)>1 else 0
            f.seek(0)
            reader = csv.reader(f, dialect)
            try:
                next(reader)
            except StopIteration:
                return results
            for row in reader:
                if not row or not any((cell or "").strip() for cell in row):
                    continue
                if len(row) <= max(idx_pred, idx_text):
                    row = row + [''] * (max(idx_pred, idx_text) - len(row) + 1)
                pred_raw = (row[idx_pred] or "").strip().lower() if idx_pred < len(row) else ""
                text = ",".join(row[idx_text:]).strip() if idx_text < len(row) else ""
                if not text:
                    continue
                max_prob = 0.0
                if idx_prob is not None and idx_prob < len(row):
                    raw = (row[idx_prob] or "").strip()
                    if raw != "":
                        s = raw.replace("%","").replace(",","").strip()
                        try:
                            p = float(s)
                            if p > 1.0:
                                p = p/100.0
                            max_prob = float(max(0.0, min(1.0, p)))
                        except:
                            max_prob = 0.0
                # normalize label
                if pred_raw in ("hawkish","hawk","h","neutral","neural","n","dovish","dove","d"):
                    # keep raw if mapped
                    if pred_raw in ("hawkish","hawk","h"):
                        label = "hawkish"
                    elif pred_raw in ("dovish","dove","d"):
                        label = "dovish"
                    elif pred_raw in ("neutral","neural","n"):
                        label = "neutral"
                    else:
                        label = pred_raw
                else:
                    if "hawk" in pred_raw:
                        label = "hawkish"
                    elif "dov" in pred_raw or "dove" in pred_raw:
                        label = "dovish"
                    elif "neu" in pred_raw:
                        label = "neutral"
                    else:
                        label = "neutral"
                results.append({"pred_label": label, "text": text, "max_prob": max_prob})
    except Exception as e:
        print(f"[read_pred_csv] ERROR reading {filepath}: {e}")
    return results

def make_text_map_with_prob(data_list):
    od = OrderedDict()
    for it in data_list:
        txt = (it.get("text","") or "").strip()
        if not txt:
            continue
        lab = (it.get("pred_label","neutral") or "neutral").strip().lower()
        prob = float(it.get("max_prob",0.0) or 0.0)
        if txt not in od:
            od[txt] = {"label": lab, "max_prob": prob}
    return od

# ---------- hawk-share (probability-weighted) using read_pred_csv output ----------
def hawk_share_from_pred_file(p):
    """
    Compute hawk_share from a pred CSV file path using read_pred_csv:
      hawk_share = sum(max_prob for hawk rows) / sum(max_prob for all rows)
    If total_prob == 0, fallback to fraction of hawk rows.
    Returns float in [0,1] or None if file missing/empty.
    """
    if not p or not os.path.isfile(p):
        return None
    rows = read_pred_csv(p)
    if not rows:
        return None
    total_prob = sum(r.get("max_prob",0.0) for r in rows)
    hawk_prob = sum(r.get("max_prob",0.0) for r in rows if "hawk" in (r.get("pred_label") or ""))
    if total_prob > 0.0:
        return float(hawk_prob / total_prob)
    # fallback to count-based
    cnt = len(rows)
    hawks = sum(1 for r in rows if "hawk" in (r.get("pred_label") or ""))
    return float(hawks / cnt) if cnt>0 else None

# ---------- find pred files by date helper ----------
def date_variants_from_string(s):
    vs = []
    m = re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})', s)
    if m:
        y,mth,d = m.group(1), m.group(2), m.group(3)
        vs.extend([y+mth+d, f"{y}-{mth}-{d}", f"{y}_{mth}_{d}"])
    m2 = re.search(r'(\d{8})', s)
    if m2:
        s8 = m2.group(1)
        if s8 not in vs:
            y,mth,d = s8[:4], s8[4:6], s8[6:8]
            vs.extend([s8, f"{y}-{mth}-{d}", f"{y}_{mth}_{d}"])
    return vs

def _search_pred_by_kind_and_date(kind, variants):
    # prefer dedicated dirs
    dirs = []
    if kind == "mone":
        dirs.append(PRED_STATEMENT_DIR)
    if kind == "pres":
        dirs.append(PRED_BLOCKS_PRES_DIR)
    dirs.extend([PRED_DIR])
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for dv in variants:
            patterns = [f"*{dv}*{kind}*.csv", f"*{kind}*{dv}*.csv", f"pred*{dv}*{kind}*.csv", f"*{dv}*.csv"]
            for pat in patterns:
                found = sorted(glob.glob(os.path.join(d, pat)))
                if found:
                    # prefer matching kind explicitly
                    for f in found:
                        bn = os.path.basename(f).lower()
                        if kind in bn or 'pred' in bn:
                            return f
                    return found[0]
    return None

def get_pred_paths_for_date(date_hint):
    """Return (stmt_path, pres_path) or (None, None)."""
    variants = date_variants_from_string(date_hint) or [date_hint]
    stmt = _search_pred_by_kind_and_date("mone", variants)
    pres = _search_pred_by_kind_and_date("pres", variants)
    return stmt, pres

# ---------- price CSV helpers: extract close robustly ----------
def _find_close_column_index_from_csv(path):
    """
    Attempt to detect a 'close' column index from header names.
    Preferred headers: 'close', 'adjclose', 'adj close', 'price'
    If header absent but rows have >=5 columns, prefer index 4.
    Returns integer index or None.
    """
    try:
        with open(path, "r", encoding="utf-8", newline='') as f:
            sample = f.read(8192); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            headers = []
            try:
                headers = next(reader)
            except StopIteration:
                headers = []
            norm = [h.strip().lower() for h in headers]
            candid = ["close","adjclose","adj close","adjusted close","price","last","px_close"]
            for c in candid:
                for i,h in enumerate(norm):
                    if c in h:
                        return i
            # if no header or header not containing known names, inspect first data row for numeric patterns
            # reset and attempt to read first non-empty row
            f.seek(0)
            reader = csv.reader(f, dialect)
            for row in reader:
                if not row or not any((c or "").strip() for c in row):
                    continue
                # if row length >=6, assume format timestamp,open,high,low,close,adjclose,vol
                if len(row) >= 5:
                    return 4  # index 4 -> close
                else:
                    # fallback to rightmost numeric if small row
                    numeric_indices = []
                    num_re = re.compile(r'[-+]?\(?\d{1,3}(?:[,\d]{0,})?(?:\.\d+)?\)?')
                    for i,cell in enumerate(row):
                        if cell and num_re.search(str(cell)):
                            numeric_indices.append(i)
                    if numeric_indices:
                        return numeric_indices[-1]
            return None
    except Exception:
        return None

def read_time_and_close_pairs(path, close_index_hint=None):
    """
    Return list of (datetime, close_float) pairs from CSV.
    Use close_index_hint if provided, else try _find_close_column_index_from_csv.
    """
    pairs = []
    if not os.path.isfile(path):
        return pairs
    try:
        with open(path, "r", encoding="utf-8", newline='') as f:
            sample = f.read(8192); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            # try header detection for close index
            headers = []
            pos = None
            try:
                headers = next(reader)
                # if header row looks textual, we consider it header
                if any(h.strip().isalpha() for h in headers if h.strip()):
                    norm = [h.strip().lower() for h in headers]
                    for cand in ("close","adjclose","adj close","price","last"):
                        for i,h in enumerate(norm):
                            if cand in h:
                                pos = i
                                break
                        if pos is not None:
                            break
                else:
                    # header not textual -> treat as data row and reposition to start
                    f.seek(0)
                    reader = csv.reader(f, dialect)
            except StopIteration:
                return pairs
            if close_index_hint is None:
                if pos is None:
                    pos = _find_close_column_index_from_csv(path)
            else:
                pos = close_index_hint
            # parse rows
            for row in reader:
                if not row or not any((c or "").strip() for c in row):
                    continue
                # timestamp candidate in first column
                tcell = str(row[0]).strip()
                dt = None
                if tcell:
                    ttry = tcell.replace(" ", "T")
                    try:
                        dt = datetime.datetime.fromisoformat(ttry)
                    except Exception:
                        for fmt in ("%Y-%m-%d %H:%M:%S%z","%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S"):
                            try:
                                dt = datetime.datetime.strptime(tcell, fmt); break
                            except Exception:
                                continue
                # extract close
                close_val = None
                if pos is not None and pos < len(row):
                    s = str(row[pos]).strip()
                    s_clean = s.replace(",","").replace("$","").strip()
                    if s_clean.startswith("(") and s_clean.endswith(")"):
                        s_clean = "-" + s_clean[1:-1]
                    try:
                        close_val = float(s_clean)
                    except:
                        close_val = None
                # fallback: rightmost numeric
                if close_val is None:
                    num_re = re.compile(r'[-+]?\(?\d{1,3}(?:[,\d]{0,})?(?:\.\d+)?\)?')
                    joined = " | ".join([str(c) for c in row])
                    matches = list(num_re.finditer(joined))
                    if matches:
                        s = matches[-1].group(0)
                        s_clean = s.replace(",","").replace("$","").strip()
                        if s_clean.startswith("(") and s_clean.endswith(")"):
                            s_clean = "-" + s_clean[1:-1]
                        try:
                            close_val = float(s_clean)
                        except:
                            close_val = None
                if dt is not None and close_val is not None:
                    pairs.append((dt, float(close_val)))
    except Exception as e:
        # safe fallback: return pairs collected so far
        # print debug
        print(f"[read_time_and_close_pairs] Error reading {path}: {e}")
        return pairs
    return pairs

# ---------- find price plot & price CSV helpers ----------
def find_plot_for_date(date_str):
    if not os.path.isdir(RESULTS_PLOTS_DIR):
        return None
    variants = date_variants_from_string(date_str) or [date_str]
    exts = ["png","jpg","jpeg"]
    for v in variants:
        for ext in exts:
            found = sorted(glob.glob(os.path.join(RESULTS_PLOTS_DIR, f"*{v}*.{ext}")))
            if found:
                return found[0]
    # fallback: year
    if len(date_str) >= 4:
        found = sorted(glob.glob(os.path.join(RESULTS_PLOTS_DIR, f"*{date_str[:4]}*.png")))
        if found:
            return found[0]
    return None

def find_candidate_csv_for_date(date_str, kind=None):
    # same as previously: prefer predicted/csv and results/csv
    search_dirs = []
    for d in [PRED_CSV_DIR, RESULTS_CSV_DIR, PRED_DIR, RESULTS_PLOTS_DIR]:
        if os.path.isdir(d) and d not in search_dirs:
            search_dirs.append(d)
    variants = date_variants_from_string(date_str) or [date_str]
    patterns = []
    for v in variants:
        patterns += [f"*1h*{v}*.csv", f"*{v}*1h*.csv", f"*{v}*ET*.csv", f"*{v}*.csv"]
    for d in search_dirs:
        for pat in patterns:
            found = sorted(glob.glob(os.path.join(d, pat)))
            if found:
                # prefer 1h in name
                for f in found:
                    if "1h" in os.path.basename(f).lower():
                        return f
                return found[0]
    return None

# ---------- annotation using pred-file hawk-share (NO OCR) ----------
def annotate_and_copy_plot(plot_src, date_hint, search_kind=None):
    """
    Uses hawk-share computed from prediction CSV files (statement & press) - no OCR.
    Draw bottom band + slanted line with GREEN or RED according to rules.
    """
    global PLOT_ANNOTATION_STATS, PLOT_ANNOTATED
    if not plot_src or not os.path.isfile(plot_src):
        return None
    basename = os.path.basename(plot_src)
    dst = os.path.join(PLOTS_WEB_DIR, basename)
    try:
        if (not os.path.exists(dst)) or (os.path.getmtime(plot_src) > os.path.getmtime(dst)):
            shutil.copy2(plot_src, dst)
    except Exception as e:
        print(f"[annotate] Warning copying plot: {e}")
        return None
    if basename in PLOT_ANNOTATED:
        return f"plots/{basename}"

    # determine date variants from plot filename first (avoid mismatch with passed date_hint)
    def _date_variants_from_filename(fname):
        vs = date_variants_from_string(os.path.basename(fname))
        return vs or date_variants_from_string(date_hint) or [date_hint]
    date_variants = _date_variants_from_filename(plot_src)

    # find matching 1h csv using date variants
    candidate_csv = None
    for dv in date_variants:
        candidate_csv = find_candidate_csv_for_date(dv, kind=search_kind)
        if candidate_csv:
            break
    if not candidate_csv:
        print(f"[annotate] No 1h CSV found for plot {basename} using variants {date_variants} -> skipping")
        PLOT_ANNOTATION_STATS["skipped"] += 1
        PLOT_ANNOTATED.add(basename)
        return f"plots/{basename}"

    # read last two time-close pairs using header-aware close column selection
    pairs = read_time_and_close_pairs(candidate_csv)
    if len(pairs) < 2:
        print(f"[annotate] Not enough timestamped rows in {candidate_csv} for {basename} -> skipping")
        PLOT_ANNOTATION_STATS["skipped"] += 1
        PLOT_ANNOTATED.add(basename)
        return f"plots/{basename}"
    t_prev, prev_close = pairs[-2]
    t_last, last_close = pairs[-1]
    change = float(last_close) - float(prev_close)

    # compute hawk-share from pred files (prefer dedicated dirs)
    stmt_path, pres_path = get_pred_paths_for_date(date_variants[0])
    # if not found for first variant, try others
    if stmt_path is None or pres_path is None:
        for dv in date_variants:
            s, p = get_pred_paths_for_date(dv)
            if stmt_path is None and s:
                stmt_path = s
            if pres_path is None and p:
                pres_path = p
            if stmt_path and pres_path:
                break

    stmt_score = hawk_share_from_pred_file(stmt_path)
    press_score = hawk_share_from_pred_file(pres_path)
    if stmt_score is None or press_score is None:
        print(f"[annotate] Could not compute hawk-share (stmt={stmt_score}, press={press_score}) for {basename} -> skipping")
        PLOT_ANNOTATION_STATS["skipped"] += 1
        PLOT_ANNOTATED.add(basename)
        return f"plots/{basename}"

    # color rule (use probability-weighted hawk-share)
    cond_green = False
    if (press_score > stmt_score and change < 0) or (press_score < stmt_score and change > 0):
        cond_green = True
    cond_red = not cond_green
    color_name = "GREEN" if cond_green else "RED"
    print(f"[annotate] {basename}: csv={os.path.basename(candidate_csv)}, t_prev={t_prev}, prev={prev_close:.6f}, t_last={t_last}, last={last_close:.6f}, change={change:.6f}, stmt={stmt_score:.4f}, press={press_score:.4f} => {color_name}")

    # draw overlay
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print("[annotate] Pillow not installed. Install with 'pip install pillow' to enable drawing.")
        PLOT_ANNOTATION_STATS["skipped"] += 1
        PLOT_ANNOTATED.add(basename)
        return f"plots/{basename}"

    try:
        im = Image.open(dst).convert("RGBA")
        w, h = im.size
        left_margin = int(w * 0.06); right_margin = int(w * 0.02)
        top_margin = int(h * 0.08); bottom_margin = int(h * 0.10)
        plot_w = w - left_margin - right_margin; plot_h = h - top_margin - bottom_margin

        # map times to x positions
        min_t = min(dt for dt,_ in pairs); max_t = max(dt for dt,_ in pairs)
        total_seconds = (max_t - min_t).total_seconds()
        if total_seconds <= 0:
            x1 = int(w*0.80); x2 = int(w*0.95)
        else:
            frac_prev = (t_prev - min_t).total_seconds() / total_seconds
            frac_last = (t_last - min_t).total_seconds() / total_seconds
            x1 = left_margin + int(frac_prev * plot_w); x2 = left_margin + int(frac_last * plot_w)

        pmin = min([c for _,c in pairs]); pmax = max([c for _,c in pairs])
        if pmax == pmin:
            pad = max(1e-6, abs(pmax)*0.01); pmin -= pad; pmax += pad
        def price_to_y(p):
            frac = (p - pmin) / (pmax - pmin); frac = max(0.0, min(1.0, frac))
            return top_margin + int((1.0 - frac) * plot_h)
        y1 = price_to_y(prev_close); y2 = price_to_y(last_close)

        overlay = Image.new("RGBA", (w,h), (255,255,255,0)); draw = ImageDraw.Draw(overlay)
        band_height = max(int(h * 0.12), 24)
        band_top = h - bottom_margin - band_height
        band_bbox = (min(x1,x2)-2, band_top, max(x1,x2)+2, h - bottom_margin + 2)
        band_color = (34,139,34,160) if cond_green else (200,30,30,160)
        draw.rectangle(band_bbox, fill=band_color)
        seg_color = (34,139,34,230) if cond_green else (200,30,30,230)
        seg_thickness = max(3, int(h*0.02))
        draw.line((x1,y1,x2,y2), fill=seg_color, width=seg_thickness)
        combined = Image.alpha_composite(im, overlay)
        combined.convert("RGB").save(dst)

        PLOT_ANNOTATION_STATS["total"] += 1
        if cond_green: PLOT_ANNOTATION_STATS["green"] += 1
        else: PLOT_ANNOTATION_STATS["red"] += 1
        PLOT_ANNOTATED.add(basename)
    except Exception as e:
        print(f"[annotate] Drawing failed for {dst}: {e}")
        PLOT_ANNOTATED.add(basename)
        PLOT_ANNOTATION_STATS["skipped"] += 1

    return f"plots/{basename}"

# ---------- HTML generators (small/simple) ----------
def generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot_rel, new_plot_rel):
    title = f"Compare {old_date} → {new_date} (mone)"
    parts = [f"<h1>{escape_html(title)}</h1>"]
    if old_plot_rel or new_plot_rel:
        parts.append("<div style='display:flex;gap:12px'>")
        if old_plot_rel: parts.append(f"<div style='flex:1'><img src='../{old_plot_rel}'></div>")
        if new_plot_rel: parts.append(f"<div style='flex:1'><img src='../{new_plot_rel}'></div>")
        parts.append("</div>")
    added = {t:new_map[t] for t in new_map if t not in old_map}
    removed = {t:old_map[t] for t in old_map if t not in new_map}
    common = {t:new_map[t] for t in new_map if t in old_map}
    parts.append("<h2>Added</h2>")
    if added:
        for t,m in added.items():
            parts.append(f'<p>{escape_html(t)} <small>({m.get("max_prob",0.0):.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")
    parts.append("<h2>Removed</h2>")
    if removed:
        for t,m in removed.items():
            parts.append(f'<p><del>{escape_html(t)}</del> <small>({m.get("max_prob",0.0):.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")
    parts.append('<p><a href="../index.html">&larr; Back</a></p>')
    return "\n".join(parts)

def generate_pres_page_html(pres_map, date_str, plot_rel):
    title = f"Pres {date_str}"
    parts = [f"<h1>{escape_html(title)}</h1>"]
    if plot_rel: parts.append(f"<div><img src='../{plot_rel}'></div>")
    parts.append("<h2>Sentences</h2>")
    if pres_map:
        for t,m in pres_map.items():
            parts.append(f'<p>{escape_html(t)} <small>({m.get("max_prob",0.0):.3f})</small></p>')
    else:
        parts.append("<p><em>No sentences found.</em></p>")
    parts.append('<p><a href="../index.html">&larr; Back</a></p>')
    return "\n".join(parts)

# ---------- dedupe scan (same as before) ----------
def scan_predicted_files():
    mone_by_date = {}
    pres_by_date = {}
    cand_dirs = [PRED_STATEMENT_DIR, PRED_BLOCKS_PRES_DIR, PRED_DIR]
    for d in cand_dirs:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            full = os.path.join(d, fname)
            if not os.path.isfile(full):
                continue
            b = os.path.basename(fname)
            m = re.search(r'(?i)pred[_-]?(\d{8})[_-]?(mone|pres)\.csv$', b)
            if m:
                date = m.group(1); kind = m.group(2).lower()
            else:
                m2 = re.search(r'(?i)(\d{8}).*(mone|pres)\.csv$', b)
                if m2:
                    date = m2.group(1); kind = m2.group(2).lower()
                else:
                    m3 = re.search(r'(\d{4})[-_](\d{2})[-_](\d{2})', b)
                    if m3:
                        date = m3.group(1) + m3.group(2) + m3.group(3)
                        kind = "mone" if "mone" in b.lower() else ("pres" if "pres" in b.lower() else None)
                    else:
                        continue
            if not date or not kind:
                continue
            if kind == "mone":
                if date not in mone_by_date:
                    mone_by_date[date] = full
                else:
                    existing = mone_by_date[date]
                    if existing.startswith(PRED_DIR) and d == PRED_STATEMENT_DIR:
                        mone_by_date[date] = full
            elif kind == "pres":
                if date not in pres_by_date:
                    pres_by_date[date] = full
                else:
                    existing = pres_by_date[date]
                    if existing.startswith(PRED_DIR) and d == PRED_BLOCKS_PRES_DIR:
                        pres_by_date[date] = full
    return mone_by_date, pres_by_date

# ---------- main ----------
def main():
    ensure_style_css(STYLE_PATH)
    mone_by_date, pres_by_date = scan_predicted_files()
    mone_dates = sorted(mone_by_date.keys())
    pres_dates = sorted(pres_by_date.keys())
    print("Found mone dates:", mone_dates)
    print("Found pres dates:", pres_dates)
    links = []

    for i in range(1, len(mone_dates)):
        old_date = mone_dates[i-1]; new_date = mone_dates[i]
        csv_new = find_candidate_csv_for_date(new_date, kind='mone')
        if not csv_new:
            print(f"[skip compare] {old_date} -> {new_date}: missing 1h CSV for {new_date}")
            continue
        old_fp = mone_by_date.get(old_date); new_fp = mone_by_date.get(new_date)
        print(f"[compare] {old_date} -> {new_date} (files: {os.path.basename(old_fp)} , {os.path.basename(new_fp)})")
        old_data = read_pred_csv(old_fp); new_data = read_pred_csv(new_fp)
        old_map = make_text_map_with_prob(old_data); new_map = make_text_map_with_prob(new_data)
        old_plot_src = find_plot_for_date(old_date); new_plot_src = find_plot_for_date(new_date)
        old_plot_rel = annotate_and_copy_plot(old_plot_src, old_date, search_kind='mone') if old_plot_src else None
        new_plot_rel = annotate_and_copy_plot(new_plot_src, new_date, search_kind='mone') if new_plot_src else None
        html = generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot_rel, new_plot_rel)
        out_name = f"compare_{old_date}_to_{new_date}_mone.html"; out_path = os.path.join(COMPARISONS_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>"+escape_html(f"Compare {old_date}->{new_date}")+"</title><link rel='stylesheet' href='../style.css'></head><body>\n")
            f.write(html); f.write("\n</body></html>")
        links.append((f"{old_date} → {new_date} (mone)", f"comparisons/{out_name}"))

    for date in pres_dates:
        pres_fp = pres_by_date.get(date)
        csv_match = find_candidate_csv_for_date(date, kind='pres')
        if not csv_match:
            print(f"[skip pres] {date}: missing 1h CSV")
            continue
        print(f"[pres page] {date} (file: {os.path.basename(pres_fp)})")
        pres_data = read_pred_csv(pres_fp)
        pres_map = make_text_map_with_prob(pres_data)
        plot_src = find_plot_for_date(date)
        plot_rel = annotate_and_copy_plot(plot_src, date, search_kind='pres') if plot_src else None
        html = generate_pres_page_html(pres_map, date, plot_rel)
        out_name = f"pres_{date}.html"; out_path = os.path.join(PRES_PAGES_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>"+escape_html(f"Pres {date}")+"</title><link rel='stylesheet' href='../style.css'></head><body>\n")
            f.write(html); f.write("\n</body></html>")
        links.append((f"Pres {date}", f"pres/{out_name}"))

    # index
    index_html = ["<!DOCTYPE html><html><head><meta charset='utf-8'><title>Index</title><link rel='stylesheet' href='style.css'></head><body>"]
    index_html.append("<h1>FOMC: mone Comparisons & pres Pages</h1>")
    if links:
        index_html.append("<ul>")
        for title,href in sorted(links):
            index_html.append(f"<li><a href='{href}'>{escape_html(title)}</a></li>")
        index_html.append("</ul>")
    else:
        index_html.append("<p>No pages generated. Place predicted files and 1h CSVs in predicted/ and plots in results/plots.</p>")
    index_html.append("</body></html>")
    with open(os.path.join(WEB_DIR,"index.html"),"w",encoding="utf-8") as f:
        f.write("\n".join(index_html))

    # final stats
    print("Index ->", os.path.join(WEB_DIR,"index.html"))
    tot = PLOT_ANNOTATION_STATS.get("total",0); g = PLOT_ANNOTATION_STATS.get("green",0); r = PLOT_ANNOTATION_STATS.get("red",0); s = PLOT_ANNOTATION_STATS.get("skipped",0)
    if tot:
        print(f"Plot annotation summary: total={tot}, green={g} ({100.0*g/tot:.1f}%), red={r} ({100.0*r/tot:.1f}%), skipped={s}")
    else:
        print(f"Plot annotation summary: total=0, skipped={s}")

if __name__ == "__main__":
    main()
