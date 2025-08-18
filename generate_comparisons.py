#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_comparisons.py (FULL)
- Compares adjacent 'mone' CSVs and creates comparison pages
- Creates per-date 'pres' pages
- Attaches plots from results/plots
- Implements:
    * percentile-based purple mapping (p50,p75,p90 from NEW file)
    * delta rule (default delta=0.03)
    * bootstrap mean-difference check (default 2000 iter) as confirmatory rule
    * page-level statistics and bootstrap CI display
"""

import os
import csv
import re
import glob
import shutil
import math
import numpy as np
from collections import OrderedDict

# ---------------- CONFIG ----------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PRED_DIR = os.path.join(PROJECT_ROOT, "predicted", "txt_pred")
RESULTS_PLOTS_DIR = os.path.join(PROJECT_ROOT, "results", "plots")
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
COMPARISONS_DIR = os.path.join(WEB_DIR, "comparisons")
PRES_PAGES_DIR = os.path.join(WEB_DIR, "pres")
PLOTS_WEB_DIR = os.path.join(WEB_DIR, "plots")
STYLE_PATH = os.path.join(WEB_DIR, "style.css")

# Threshold / bootstrap config
DELTA = 0.03                # 기본 델타 규칙
BOOTSTRAP_ITERS = 2000      # 부트스트랩 반복수
BOOTSTRAP_MIN_SAMPLES = 5   # 부트스트랩 수행 최소 샘플 수 in each group

# Create dirs
os.makedirs(COMPARISONS_DIR, exist_ok=True)
os.makedirs(PRES_PAGES_DIR, exist_ok=True)
os.makedirs(PLOTS_WEB_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)

# Sentiment fallback scoring
SENT_SCORE = {
    "hawkish": 3, "hawk": 3, "h": 3,
    "neutral": 2, "neural": 2, "n": 2,
    "dovish": 1, "dove": 1, "d": 1
}
PROB_COL_CANDIDATES = ["max_prob", "prob", "probability", "score", "confidence", "maxprob", "pred_prob"]

# ---------------- Helpers: file & csv ----------------
def extract_date_and_type(fname):
    b = os.path.basename(fname)
    m = re.search(r'(?i)pred[_-]?(\d{8})[_-]?(mone|pres)\.csv$', b)
    if m:
        return m.group(1), m.group(2).lower()
    m2 = re.search(r'(?i)(\d{8}).*(mone|pres)\.csv$', b)
    if m2:
        return m2.group(1), m2.group(2).lower()
    m3 = re.search(r'(?i)(\d{8})', b)
    m4 = re.search(r'(?i)(mone|pres)', b)
    if m3 and m4:
        return m3.group(1), m4.group(1).lower()
    return None, None

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
    Return list of dicts: {"pred_label":..., "text":..., "max_prob":float}
    """
    results = []
    try:
        with open(filepath, "r", encoding="utf-8", newline='') as f:
            sample = f.read(8192)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            try:
                headers = next(reader)
            except StopIteration:
                headers = []
            norm_headers = [h.strip().lower() for h in headers]
            # find indices
            def find_any(cands):
                for c in cands:
                    if c in norm_headers:
                        return norm_headers.index(c)
                return None
            idx_pred = find_any(["pred_label", "predlabel", "pred", "label"])
            idx_text = find_any(["text", "content", "sentence", "body"])
            idx_prob = find_prob_column_index(headers)
            if idx_text is None:
                idx_text = len(headers) - 1 if headers else 0
            if idx_pred is None:
                idx_pred = 1 if len(headers) > 1 else 0

            # Reset file read to parse rows properly with csv module
            f.seek(0)
            reader = csv.reader(f, dialect)
            # skip header we already consumed
            try:
                next(reader)
            except StopIteration:
                return results

            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                # pad
                if len(row) <= max(idx_pred, idx_text):
                    row = row + [''] * (max(idx_pred, idx_text) - len(row) + 1)
                pred_raw = row[idx_pred].strip().lower() if idx_pred < len(row) else ""
                text = ",".join(row[idx_text:]).strip() if idx_text < len(row) else ""
                if not text:
                    continue
                # parse prob
                max_prob = 0.0
                if idx_prob is not None and idx_prob < len(row):
                    raw = row[idx_prob].strip()
                    if raw != "":
                        s = raw.replace("%","").replace(",","").strip()
                        try:
                            p = float(s)
                            if p > 1.0:
                                p = p / 100.0
                            max_prob = float(max(0.0, min(1.0, p)))
                        except:
                            max_prob = 0.0
                # normalize label
                if pred_raw in SENT_SCORE:
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
    except FileNotFoundError:
        print(f"ERROR: file not found: {filepath}")
    except Exception as e:
        print(f"ERROR reading {filepath}: {e}")
    return results

def make_text_map_with_prob(data_list):
    od = OrderedDict()
    for it in data_list:
        txt = it.get("text","").strip()
        if not txt:
            continue
        lab = it.get("pred_label","neutral").strip().lower()
        prob = float(it.get("max_prob", 0.0) or 0.0)
        if txt not in od:
            od[txt] = {"label": lab, "max_prob": prob}
    return od

# ---------------- Helpers: HTML legend ----------------
def get_legend_html():
    return """
<div class="legend-box">
  <h2>Legend: Interpretation of Colors and Intensities</h2>
  <ul>
    <li><span class="legend-sample bg-dovish-2">Dovish (green)</span>: Suggests easing, lower rates, or accommodative policy stance.</li>
    <li><span class="legend-sample bg-neutral-2">Neutral (yellow)</span>: Balanced or data-dependent stance, neither clearly dovish nor hawkish.</li>
    <li><span class="legend-sample bg-hawkish-2">Hawkish (red)</span>: Indicates tightening, higher rates, or restrictive policy stance.</li>
  </ul>
  <p>
    <strong>Color intensity</strong> (lighter → darker) reflects <strong>strength of stance</strong>:  
    darker shades = stronger signal.  
    <br>
    <span class="legend-sample bg-purple-2">Purple highlight</span> shows added sentences that are stronger than the removed ones.
  </p>
</div>
"""

# ---------------- Helpers: plotting files ----------------
def find_and_copy_plot_for_date(date_str):
    """
    Try variants: YYYYMMDD, YYYY-MM-DD, YYYY_MM_DD
    Copy first match (png/jpg/jpeg) into web/plots and return 'plots/<basename>' or None
    """
    if not os.path.isdir(RESULTS_PLOTS_DIR):
        return None
    y = date_str[0:4] if len(date_str)>=8 else None
    m = date_str[4:6] if len(date_str)>=8 else None
    d = date_str[6:8] if len(date_str)>=8 else None
    candidates = []
    if y and m and d:
        candidates = [f"{y}{m}{d}", f"{y}-{m}-{d}", f"{y}_{m}_{d}"]
    else:
        candidates = [date_str]
    exts = ["png","jpg","jpeg"]
    matches = []
    for cand in candidates:
        for ext in exts:
            pattern = os.path.join(RESULTS_PLOTS_DIR, f"*{cand}*.{ext}")
            found = sorted(glob.glob(pattern))
            if found:
                matches.extend(found)
        if matches:
            break
    if not matches and y:
        loose = sorted(glob.glob(os.path.join(RESULTS_PLOTS_DIR, f"*{y}*.png")))
        if loose:
            matches = loose
    if not matches:
        return None
    src = matches[0]
    basename = os.path.basename(src)
    dst = os.path.join(PLOTS_WEB_DIR, basename)
    try:
        if (not os.path.exists(dst)) or (os.path.getmtime(src) > os.path.getmtime(dst)):
            shutil.copy2(src, dst)
    except Exception as e:
        print(f"Warning: failed to copy plot {src} -> {dst}: {e}")
        return None
    return f"plots/{basename}"

# ---------------- Helpers: HTML / CSS ----------------
def ensure_style_css(path):
    if os.path.exists(path):
        return
    css = """
/* web/style.css (auto-generated) */
body { font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 24px; color: #111; background: #fff; }
h1 { font-size: 1.4rem; margin-bottom: 6px; }
h2 { margin-top: 16px; font-size: 1.05rem; }
.sent-text { font-size: 0.98rem; padding: 8px; border-radius: 6px; display: block; margin: 6px 0; }
.hawkish { color: #8b0000; } .neutral { color: #8a6b00; } .dovish { color: #0a6f0a; }
.bg-hawkish-1 { background: rgba(179,0,0,0.06);} .bg-hawkish-2 { background: rgba(179,0,0,0.14);} .bg-hawkish-3 { background: rgba(179,0,0,0.24);}
.bg-neutral-1 { background: rgba(166,124,0,0.06);} .bg-neutral-2 { background: rgba(166,124,0,0.14);} .bg-neutral-3 { background: rgba(166,124,0,0.24);}
.bg-dovish-1 { background: rgba(10,122,10,0.06);} .bg-dovish-2 { background: rgba(10,122,10,0.14);} .bg-dovish-3 { background: rgba(10,122,10,0.24);}
.bg-purple-1 { background: rgba(200,170,240,0.10);} .bg-purple-2 { background: rgba(160,120,220,0.18);} .bg-purple-3 { background: rgba(120,80,200,0.26);} .bg-purple-4 { background: rgba(70,30,150,0.38);}
.removed del { text-decoration: line-through; color: inherit; }
.comparison.highlight { border-left: 6px solid purple; padding-left: 10px; border-radius: 4px; background: rgba(128,0,128,0.03); }
.plot-row { display:flex; gap:12px; align-items:flex-start; margin-bottom:12px; } .plot-row img { max-width:48%; height:auto; border:1px solid #ddd; border-radius:6px; }
.plot-single img { max-width:80%; height:auto; border:1px solid #ddd; border-radius:6px; }
.stats-box { border:1px solid #ddd; padding:8px; border-radius:6px; background:#fafafa; margin:8px 0; }
.note { font-size:0.95rem; color:purple; font-weight:bold; margin-bottom:8px; }
a { color:#0b5bd7; text-decoration:none;} a:hover{ text-decoration:underline;}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)

def escape_html(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#39;"))

def bg_class_for_label(label):
    score = SENT_SCORE.get(label, 2)
    if score < 1: score = 1
    if score > 3: score = 3
    return f"bg-{label}-{score}"

def purple_class_for_prob_with_thresholds(prob, thresholds):
    # thresholds = dict with p50,p75,p90
    try:
        p = float(prob)
    except:
        p = 0.0
    p50 = thresholds.get("p50", 0.5)
    p75 = thresholds.get("p75", 0.75)
    p90 = thresholds.get("p90", 0.9)
    if p >= p90:
        return "bg-purple-4"
    if p >= p75:
        return "bg-purple-3"
    if p >= p50:
        return "bg-purple-2"
    return "bg-purple-1"

# ---------------- Stats & bootstrap ----------------
def bootstrap_mean_diff(a, b, n_iter=2000):
    """
    Return bootstrap distribution of mean(a)-mean(b) (numpy array)
    Requires len(a) >= BOOTSTRAP_MIN_SAMPLES and len(b) >= BOOTSTRAP_MIN_SAMPLES to be meaningful
    """
    a = np.array(a); b = np.array(b)
    if len(a) < BOOTSTRAP_MIN_SAMPLES or len(b) < BOOTSTRAP_MIN_SAMPLES:
        return None
    rng = np.random.default_rng(0)
    out = []
    na = len(a); nb = len(b)
    for _ in range(n_iter):
        sa = rng.choice(a, size=na, replace=True)
        sb = rng.choice(b, size=nb, replace=True)
        out.append(sa.mean() - sb.mean())
    return np.array(out)

# ---------------- HTML generators ----------------
def generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot, new_plot):
    added = {t: new_map[t] for t in new_map if t not in old_map}
    removed = {t: old_map[t] for t in old_map if t not in new_map}
    common = {t: new_map[t] for t in new_map if t in old_map}

    # stats
    def stats_of(mapping):
        if not mapping:
            return {"count":0,"mean":None,"median":None,"min":None,"max":None,"std":None}
        probs = np.array([v.get("max_prob",0.0) for v in mapping.values()], dtype=float)
        return {"count": int(len(probs)),
                "mean": float(np.mean(probs)),
                "median": float(np.median(probs)),
                "min": float(np.min(probs)),
                "max": float(np.max(probs)),
                "std": float(np.std(probs, ddof=1)) if len(probs)>1 else 0.0}

    added_stats = stats_of(added)
    removed_stats = stats_of(removed)

    # percentile thresholds computed from NEW file distribution
    new_probs = np.array([v.get("max_prob",0.0) for v in new_map.values()], dtype=float)
    if len(new_probs)>0:
        p50 = float(np.percentile(new_probs,50))
        p75 = float(np.percentile(new_probs,75))
        p90 = float(np.percentile(new_probs,90))
    else:
        p50,p75,p90 = 0.5,0.75,0.9
    thresholds = {"p50":p50,"p75":p75,"p90":p90}

    # delta rule
    added_max = added_stats["max"] if added_stats["count"]>0 else 0.0
    removed_max = removed_stats["max"] if removed_stats["count"]>0 else 0.0
    delta_flag = (added_max > (removed_max + DELTA))

    # bootstrap
    added_probs = [v.get("max_prob",0.0) for v in added.values()]
    removed_probs = [v.get("max_prob",0.0) for v in removed.values()]
    boot = bootstrap_mean_diff(added_probs, removed_probs, n_iter=BOOTSTRAP_ITERS)
    if boot is not None:
        boot_mean = float(np.mean(boot))
        boot_lo = float(np.percentile(boot,2.5))
        boot_hi = float(np.percentile(boot,97.5))
        bootstrap_flag = (boot_lo > 0.0)
    else:
        boot_mean, boot_lo, boot_hi = None, None, None
        bootstrap_flag = False

    added_stronger = delta_flag or bootstrap_flag

    # build html
    title = f"Compare {old_date} → {new_date} (mone)"
    parts = []
    parts.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>{escape_html(title)}</title>")
    parts.append('<link rel="stylesheet" type="text/css" href="../style.css">')
    parts.append("</head><body>")
    parts.append(f"<h1>{escape_html(title)}</h1>")

    # plots
    if old_plot or new_plot:
        parts.append('<div class="plot-row">')
        if old_plot:
            parts.append(f'<div class="plot-single"><img src="../{old_plot}" alt="plot {old_date}"></div>')
        if new_plot:
            parts.append(f'<div class="plot-single"><img src="../{new_plot}" alt="plot {new_date}"></div>')
        parts.append('</div>')

    # stats box
    parts.append('<div class="stats-box">')
    parts.append(f'<strong>Stats</strong>: Added count={added_stats["count"]}, Removed count={removed_stats["count"]}, Common count={len(common)}<br>')
    parts.append(f'Added mean/median/max = {fmt(added_stats["mean"])}/{fmt(added_stats["median"])}/{fmt(added_stats["max"])}; ')
    parts.append(f'Removed mean/median/max = {fmt(removed_stats["mean"])}/{fmt(removed_stats["median"])}/{fmt(removed_stats["max"])}<br>')
    parts.append(f'Percentile thresholds (new file): p50={p50:.3f}, p75={p75:.3f}, p90={p90:.3f}<br>')
    parts.append(f'Delta rule: added_max ({added_max:.3f}) > removed_max ({removed_max:.3f}) + DELTA ({DELTA}) => {delta_flag}<br>')
    if boot_mean is not None:
        parts.append(f'Bootstrap mean diff = {boot_mean:.4f}, 95% CI = ({boot_lo:.4f}, {boot_hi:.4f}), bootstrap_flag={bootstrap_flag}<br>')
    else:
        parts.append(f'Bootstrap: not run (need at least {BOOTSTRAP_MIN_SAMPLES} samples each).<br>')
    parts.append(f'<strong>Final added_stronger = {added_stronger}</strong>')
    parts.append('</div>')

    # container highlight if added_stronger
    if added_stronger:
        parts.append('<div class="comparison highlight">')
        parts.append('<p class="note">⚠️ Added sentences judged stronger (delta or bootstrap). Purple backgrounds used (intensity ∝ max_prob).</p>')
    else:
        parts.append('<div class="comparison">')

    # Added
    parts.append("<h2>Added sentences</h2>")
    if added:
        for text, meta in added.items():
            lab = meta.get("label","neutral")
            prob = meta.get("max_prob",0.0)
            if added_stronger:
                bgcls = purple_class_for_prob_with_thresholds(prob, thresholds)
            else:
                bgcls = bg_class_for_label(lab)
            textcls = f"sent-text {lab}"
            parts.append(f'<p class="{bgcls}"><span class="{textcls}">{escape_html(text)}</span> <small>({prob:.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")

    # Removed
    parts.append("<h2>Removed sentences</h2>")
    if removed:
        for text, meta in removed.items():
            lab = meta.get("label","neutral")
            prob = meta.get("max_prob",0.0)
            bgcls = bg_class_for_label(lab)
            textcls = f"sent-text {lab}"
            parts.append(f'<p class="{bgcls}"><span class="{textcls}"><del>{escape_html(text)}</del></span> <small>({prob:.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")

    # Common
    parts.append("<h2>Common sentences</h2>")
    if common:
        for text, meta in common.items():
            lab = meta.get("label","neutral")
            prob = meta.get("max_prob",0.0)
            bgcls = bg_class_for_label(lab)
            textcls = f"sent-text {lab}"
            parts.append(f'<p class="{bgcls}"><span class="{textcls}">{escape_html(text)}</span> <small>({prob:.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")

    parts.append("</div>")  # comparison
    parts.append('<p style="margin-top:12px;"><a href="../index.html">&larr; Back to index</a></p>')
    parts.append("</body></html>")

    return "\n".join(parts)

def generate_pres_page_html(pres_map, date_str, plot_relpath):
    title = f"Pres {date_str}"
    parts = []
    parts.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>{escape_html(title)}</title>")
    parts.append('<link rel="stylesheet" type="text/css" href="../style.css">')
    parts.append("</head><body>")
    parts.append(f"<h1>{escape_html(title)}</h1>")
    if plot_relpath:
        parts.append('<div class="plot-single">')
        parts.append(f'<img src="../{plot_relpath}" alt="plot {date_str}">')
        parts.append('</div>')
    parts.append("<h2>Sentences</h2>")
    if pres_map:
        for text, meta in pres_map.items():
            lab = meta.get("label","neutral")
            prob = meta.get("max_prob",0.0)
            bgcls = bg_class_for_label(lab)
            textcls = f"sent-text {lab}"
            parts.append(f'<p class="{bgcls}"><span class="{textcls}">{escape_html(text)}</span> <small>({prob:.3f})</small></p>')
    else:
        parts.append("<p><em>No sentences found in CSV.</em></p>")
    parts.append('<p style="margin-top:12px;"><a href="../index.html">&larr; Back to index</a></p>')
    parts.append("</body></html>")
    return "\n".join(parts)

# ---------------- utility ----------------
def fmt(x):
    return ("{:.3f}".format(x) if (x is not None and not (isinstance(x,float) and math.isnan(x))) else "N/A")

# ---------------- Main ----------------
def main():
    if not os.path.isdir(PRED_DIR):
        print("ERROR: predicted directory not found:", PRED_DIR)
        return

    # scan pred folder
    all_files = []
    for fname in sorted(os.listdir(PRED_DIR)):
        full = os.path.join(PRED_DIR, fname)
        if not os.path.isfile(full):
            continue
        date_str, kind = extract_date_and_type(fname)
        if date_str and kind:
            all_files.append((full, date_str, kind))
    all_files = sorted(all_files, key=lambda x: (x[1], x[2], os.path.basename(x[0])))

    # separate
    mone_files = [(fp, dt) for fp, dt, k in all_files if k == "mone"]
    pres_files = [(fp, dt) for fp, dt, k in all_files if k == "pres"]

    print("Found files:")
    print("  mone:", [os.path.basename(x[0]) for x in mone_files])
    print("  pres:", [os.path.basename(x[0]) for x in pres_files])

    ensure_style_css(STYLE_PATH)

    links = []

    # process mone comparisons
    for i in range(1, len(mone_files)):
        old_fp, old_date = mone_files[i-1]
        new_fp, new_date = mone_files[i]
        print(f"Comparing mone: {old_date} -> {new_date}")

        old_data = read_pred_csv(old_fp)
        new_data = read_pred_csv(new_fp)
        old_map = make_text_map_with_prob(old_data)
        new_map = make_text_map_with_prob(new_data)

        old_plot = find_and_copy_plot_for_date(old_date)
        new_plot = find_and_copy_plot_for_date(new_date)

        out_name = f"compare_{old_date}_to_{new_date}_mone.html"
        out_path = os.path.join(COMPARISONS_DIR, out_name)
        html = generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot, new_plot)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        links.append(f'<li><a href="comparisons/{out_name}">{old_date} → {new_date} (mone)</a></li>')

    # process pres files (single pages)
    for pres_fp, pres_date in pres_files:
        print(f"Generating pres page for {pres_date}")
        pres_data = read_pred_csv(pres_fp)
        pres_map = make_text_map_with_prob(pres_data)
        plot_rel = find_and_copy_plot_for_date(pres_date)
        out_name = f"pres_{pres_date}.html"
        out_path = os.path.join(PRES_PAGES_DIR, out_name)
        html = generate_pres_page_html(pres_map, pres_date, plot_rel)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        links.append(f'<li><a href="pres/{out_name}">Pres {pres_date}</a></li>')

    # index
    index_parts = []
    index_parts.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    index_parts.append("<title>FOMC: mone Comparisons & pres Pages</title>")
    index_parts.append('<link rel="stylesheet" type="text/css" href="style.css">')
    index_parts.append("</head><body>")
    index_parts.append("<h1>FOMC: mone Comparisons & pres Pages</h1>")
    index_parts.append("<h2>Available pages</h2>")
    index_parts.append("<ul>")
    if links:
        for l in sorted(links):
            index_parts.append(l)
    else:
        index_parts.append("<li>No pages generated. Put pred_YYYYMMDDmone.csv and/or pred_YYYYMMDDpres.csv into predicted/txt_pred/</li>")
    index_parts.append("</ul>")
    index_parts.append("</body></html>")

    with open(os.path.join(WEB_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_parts))

    print("Done. Generated pages in:", WEB_DIR)
    print(" - Comparisons:", COMPARISONS_DIR)
    print(" - Pres pages:", PRES_PAGES_DIR)
    print(" - Plots copied to:", PLOTS_WEB_DIR)
    print("Index ->", os.path.join(WEB_DIR, "index.html"))

if __name__ == "__main__":
    main()
