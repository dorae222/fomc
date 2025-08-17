#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_comparisons.py

- Compare adjacent 'mone' pred CSVs and generate comparison pages (web/comparisons).
- Create per-date 'pres' pages (web/pres/pres_YYYYMMDD.html) and link them from index.
- For every generated page, try to attach the PNG from PROJECT_ROOT/results/plots that contains the date string.
  If found, copy it to web/plots/ and display it at the top of the page.
- Styling handled via web/style.css (auto-created if missing).
"""

import os
import csv
import re
import glob
import shutil
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

os.makedirs(COMPARISONS_DIR, exist_ok=True)
os.makedirs(PRES_PAGES_DIR, exist_ok=True)
os.makedirs(PLOTS_WEB_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)

# sentiment scoring for strength
SENT_SCORE = {
    "hawkish": 3,
    "hawk": 3,
    "neutral": 2,
    "neural": 2,
    "dovish": 1,
    "dove": 1
}

# ---------------- Helpers ----------------
def extract_date_and_type(fname):
    """
    Extract (YYYYMMDD, kind) where kind is 'mone' or 'pres'. Flexible patterns.
    """
    b = os.path.basename(fname)
    # try strict pattern first
    m = re.search(r'(?i)pred[_-]?(\d{8})[_-]?(mone|pres)\.csv$', b)
    if m:
        return m.group(1), m.group(2).lower()
    # fallback: any 8-digit date and mone/pres later in filename
    m2 = re.search(r'(?i)(\d{8}).*(mone|pres)\.csv$', b)
    if m2:
        return m2.group(1), m2.group(2).lower()
    # last resort: any 8-digit date and presence of the word mone/pres anywhere
    m3 = re.search(r'(?i)(\d{8})', b)
    m4 = re.search(r'(?i)(mone|pres)', b)
    if m3 and m4:
        return m3.group(1), m4.group(1).lower()
    return None, None

def read_pred_csv(filepath):
    """
    Read CSV robustly and return list of {"pred_label": label, "text": text}
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
                return results
            norm_headers = [h.strip().lower() for h in headers]
            def find_idx(cands):
                for c in cands:
                    if c in norm_headers:
                        return norm_headers.index(c)
                return None
            idx_pred = find_idx(["pred_label", "predlabel", "pred", "label"])
            idx_text = find_idx(["text", "content", "sentence", "body"])
            if idx_text is None:
                idx_text = len(headers) - 1
            if idx_pred is None:
                idx_pred = 1 if len(headers) > 1 else 0
            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                if len(row) <= max(idx_pred, idx_text):
                    row = row + [''] * (max(idx_pred, idx_text) - len(row) + 1)
                pred_raw = row[idx_pred].strip().lower()
                text = ",".join(row[idx_text:]).strip()
                if not text:
                    continue
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
                results.append({"pred_label": label, "text": text})
    except FileNotFoundError:
        print(f"ERROR: file not found: {filepath}")
    except Exception as e:
        print(f"ERROR reading {filepath}: {e}")
    return results

def make_text_map(data_list):
    """
    Return OrderedDict{text: label} preserving first occurrence order.
    """
    od = OrderedDict()
    for item in data_list:
        txt = item["text"].strip()
        lab = item["pred_label"].strip().lower()
        if txt and txt not in od:
            od[txt] = lab
    return od

def ensure_style_css(path):
    """
    Create style.css if missing. Includes plot image styling.
    """
    if os.path.exists(path):
        return
    css = """
/* web/style.css (auto-generated) */
body { font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 24px; color: #111; background: #fff; }
h1 { font-size: 1.4rem; margin-bottom: 6px; }
h2 { margin-top: 16px; font-size: 1.05rem; }

/* small colored text (sentiment) */
.sent-text { font-size: 0.98rem; padding: 8px; border-radius: 6px; display: block; margin: 6px 0; }

/* text color indicators */
.hawkish { color: #8b0000; }
.neutral { color: #8a6b00; }
.dovish  { color: #0a6f0a; }

/* background intensity - 3 levels */
.bg-hawkish-1 { background: rgba(179, 0, 0, 0.06); }
.bg-hawkish-2 { background: rgba(179, 0, 0, 0.14); }
.bg-hawkish-3 { background: rgba(179, 0, 0, 0.24); }

.bg-neutral-1 { background: rgba(166, 124, 0, 0.06); }
.bg-neutral-2 { background: rgba(166, 124, 0, 0.14); }
.bg-neutral-3 { background: rgba(166, 124, 0, 0.24); }

.bg-dovish-1 { background: rgba(10, 122, 10, 0.06); }
.bg-dovish-2 { background: rgba(10, 122, 10, 0.14); }
.bg-dovish-3 { background: rgba(10, 122, 10, 0.24); }

/* removed strike style keeps color */
.removed del { text-decoration: line-through; color: inherit; }

/* highlight container when added stronger */
.comparison.highlight { border-left: 6px solid purple; padding-left: 10px; border-radius: 4px; background: rgba(128,0,128,0.03); }

/* plot image style */
.plot-row { display:flex; gap:12px; align-items:flex-start; margin-bottom:12px; }
.plot-row img { max-width: 48%; height: auto; border: 1px solid #ddd; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }

/* pres page plot */
.plot-single img { max-width: 80%; height:auto; border: 1px solid #ddd; border-radius: 6px; }

/* small helper */
.note { font-size: 0.95rem; color: purple; font-weight: bold; margin-bottom: 8px; }
a { color: #0b5bd7; text-decoration: none; }
a:hover { text-decoration: underline; }
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)

def escape_html(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;"))

def bg_class_for_label(label):
    """
    Map label to background class using SENT_SCORE (1..3).
    """
    score = SENT_SCORE.get(label, 2)
    if score < 1: score = 1
    if score > 3: score = 3
    return f"bg-{label}-{score}"

def find_and_copy_plot_for_date(date_str):
    """
    Robust search for plot files matching the date.
    Accepts date_str in YYYYMMDD (from CSV filename). Tries:
      - '*YYYYMMDD*.png' (original)
      - '*YYYY-MM-DD*.png' (hyphenated)
      - '*YYYY_MM_DD*.png' (underscored)
      - also checks .jpg
    Copies the first match into web/plots/ and returns 'plots/<basename>' (relative path used in pages).
    Returns None if no match found.
    """
    # Ensure RESULTS_PLOTS_DIR and PLOTS_WEB_DIR are defined in the script scope
    global RESULTS_PLOTS_DIR, PLOTS_WEB_DIR
    if not os.path.isdir(RESULTS_PLOTS_DIR):
        return None

    # build alternative date representations
    try:
        # date_str expected like '20250730' (YYYYMMDD)
        y = date_str[0:4]
        m = date_str[4:6]
        d = date_str[6:8]
    except Exception:
        # fallback: if date_str isn't 8 chars, just try to match it literally
        y, m, d = None, None, None

    candidates = []
    if y and m and d:
        hyphen = f"{y}-{m}-{d}"
        underscore = f"{y}_{m}_{d}"
        compact = f"{y}{m}{d}"
        # order: exact compact, hyphen, underscore
        candidates.extend([compact, hyphen, underscore])
    else:
        candidates.append(date_str)

    # also include lowercase/uppercase variants not necessary for filenames but keep
    exts = ["png", "jpg", "jpeg"]

    matches = []
    for cand in candidates:
        for ext in exts:
            pattern = os.path.join(RESULTS_PLOTS_DIR, f"*{cand}*.{ext}")
            found = sorted(glob.glob(pattern))
            if found:
                matches.extend(found)
        if matches:
            break

    if not matches:
        # last resort: try any file containing the 4-digit year only (less strict)
        if y:
            loose_pattern = os.path.join(RESULTS_PLOTS_DIR, f"*{y}*.png")
            found_loose = sorted(glob.glob(loose_pattern))
            if found_loose:
                matches = found_loose

    if not matches:
        return None

    src = matches[0]
    basename = os.path.basename(src)
    dst = os.path.join(PLOTS_WEB_DIR, basename)

    try:
        # copy if dst missing or src newer
        if (not os.path.exists(dst)) or (os.path.getmtime(src) > os.path.getmtime(dst)):
            shutil.copy2(src, dst)
    except Exception as e:
        print(f"Warning: failed to copy plot {src} -> {dst}: {e}")
        return None

    return f"plots/{basename}"

# ---------------- HTML generation ----------------
def generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot, new_plot):
    added = {t: new_map[t] for t in new_map if t not in old_map}
    removed = {t: old_map[t] for t in old_map if t not in new_map}
    common = {t: new_map[t] for t in new_map if t in old_map}

    def avg_strength(mapping):
        if not mapping:
            return 0.0
        s = 0.0
        c = 0
        for lab in mapping.values():
            s += SENT_SCORE.get(lab, 2)
            c += 1
        return s / c if c else 0.0

    avg_added = avg_strength(added)
    avg_removed = avg_strength(removed)
    highlight = avg_added > avg_removed

    title = f"Compare {old_date} → {new_date} (mone)"

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html><head><meta charset='utf-8'>")
    parts.append(f"<title>{escape_html(title)}</title>")
    parts.append('<link rel="stylesheet" type="text/css" href="../style.css">')
    parts.append("</head><body>")
    parts.append(f"<h1>{escape_html(title)}</h1>")

    # plots row (if any)
    if old_plot or new_plot:
        parts.append('<div class="plot-row">')
        if old_plot:
            # from comparisons page location: ../plots/<file>
            parts.append(f'<div class="plot-single"><img src="../{old_plot}" alt="plot {old_date}"></div>')
        if new_plot:
            parts.append(f'<div class="plot-single"><img src="../{new_plot}" alt="plot {new_date}"></div>')
        parts.append('</div>')

    if highlight:
        parts.append('<div class="comparison highlight">')
        parts.append('<p class="note">⚠️ Added sentences are stronger (on average) than removed sentences — page highlighted.</p>')
    else:
        parts.append('<div class="comparison">')

    # Added
    parts.append("<h2>Added sentences</h2>")
    if added:
        for text, lab in added.items():
            cls_bg = bg_class_for_label(lab)
            cls_text = f"sent-text {lab}"
            parts.append(f'<p class="{cls_bg}"><span class="{cls_text}">{escape_html(text)}</span></p>')
    else:
        parts.append("<p><em>None</em></p>")

    # Removed
    parts.append("<h2>Removed sentences</h2>")
    if removed:
        for text, lab in removed.items():
            cls_bg = bg_class_for_label(lab)
            cls_text = f"sent-text {lab}"
            parts.append(f'<p class="{cls_bg}"><span class="{cls_text}"><del>{escape_html(text)}</del></span></p>')
    else:
        parts.append("<p><em>None</em></p>")

    # Common
    parts.append("<h2>Common sentences</h2>")
    if common:
        for text, lab in common.items():
            cls_bg = bg_class_for_label(lab)
            cls_text = f"sent-text {lab}"
            parts.append(f'<p class="{cls_bg}"><span class="{cls_text}">{escape_html(text)}</span></p>')
    else:
        parts.append("<p><em>None</em></p>")

    parts.append("</div>")  # comparison
    parts.append('<p style="margin-top:12px;"><a href="../index.html">&larr; Back to index</a></p>')
    parts.append("</body></html>")
    return "\n".join(parts)

def generate_pres_page_html(pres_map, date_str, plot_relpath):
    """
    Single pres date page: show plot (if any), list all sentences with sentiment color/bg
    """
    title = f"Pres {date_str}"
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html><head><meta charset='utf-8'>")
    parts.append(f"<title>{escape_html(title)}</title>")
    parts.append('<link rel="stylesheet" type="text/css" href="../style.css">')
    parts.append("</head><body>")
    parts.append(f"<h1>{escape_html(title)}</h1>")

    if plot_relpath:
        # pres page is under web/pres so relative path to plot is ../plots/<file>
        parts.append('<div class="plot-single">')
        parts.append(f'<img src="../{plot_relpath}" alt="plot {date_str}">')
        parts.append('</div>')

    parts.append("<h2>Sentences</h2>")
    if pres_map:
        for text, lab in pres_map.items():
            cls_bg = bg_class_for_label(lab)
            cls_text = f"sent-text {lab}"
            parts.append(f'<p class="{cls_bg}"><span class="{cls_text}">{escape_html(text)}</span></p>')
    else:
        parts.append("<p><em>No sentences found in CSV.</em></p>")

    parts.append('<p style="margin-top:12px;"><a href="../index.html">&larr; Back to index</a></p>')
    parts.append("</body></html>")
    return "\n".join(parts)

# ---------------- Main ----------------
def main():
    if not os.path.isdir(PRED_DIR):
        print("ERROR: predicted directory not found:", PRED_DIR)
        return

    # collect pred CSVs
    all_files = []
    for fname in sorted(os.listdir(PRED_DIR)):
        full = os.path.join(PRED_DIR, fname)
        if not os.path.isfile(full):
            continue
        date_str, kind = extract_date_and_type(fname)
        if date_str and kind:
            all_files.append((full, date_str, kind))
    # sort by date then kind
    all_files = sorted(all_files, key=lambda x: (x[1], x[2], os.path.basename(x[0])))

    # separate lists
    mone_files = [(fp, dt) for fp, dt, k in all_files if k == "mone"]
    pres_files = [(fp, dt) for fp, dt, k in all_files if k == "pres"]

    print("Found files:")
    print("  mone:", [os.path.basename(x[0]) for x in mone_files])
    print("  pres:", [os.path.basename(x[0]) for x in pres_files])

    ensure_style_css(STYLE_PATH)

    links = []

    # Process mone comparisons (adjacent pairs)
    for i in range(1, len(mone_files)):
        old_fp, old_date = mone_files[i-1]
        new_fp, new_date = mone_files[i]
        print(f"Comparing mone: {old_date} -> {new_date}")

        old_data = read_pred_csv(old_fp)
        new_data = read_pred_csv(new_fp)
        old_map = make_text_map(old_data)
        new_map = make_text_map(new_data)

        # find plots for both dates
        old_plot = find_and_copy_plot_for_date(old_date)
        new_plot = find_and_copy_plot_for_date(new_date)

        out_fname = f"compare_{old_date}_to_{new_date}_mone.html"
        out_path = os.path.join(COMPARISONS_DIR, out_fname)
        html = generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot, new_plot)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        links.append(f'<li><a href="comparisons/{out_fname}">{old_date} → {new_date} (mone)</a></li>')

    # Process pres files: create a dedicated page per date (no comparison)
    for pres_fp, pres_date in pres_files:
        print(f"Generating pres page for {pres_date}")
        pres_data = read_pred_csv(pres_fp)
        pres_map = make_text_map(pres_data)
        # find and copy plot
        plot_rel = find_and_copy_plot_for_date(pres_date)
        out_fname = f"pres_{pres_date}.html"
        out_path = os.path.join(PRES_PAGES_DIR, out_fname)
        html = generate_pres_page_html(pres_map, pres_date, plot_rel)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        links.append(f'<li><a href="pres/{out_fname}">Pres {pres_date}</a></li>')

    # Generate index (show mone comparisons and pres links)
    index_parts = []
    index_parts.append("<!DOCTYPE html>")
    index_parts.append("<html><head><meta charset='utf-8'>")
    index_parts.append("<title>FOMC Comparisons & Pres Pages</title>")
    index_parts.append('<link rel="stylesheet" type="text/css" href="style.css">')
    index_parts.append("</head><body>")
    index_parts.append("<h1>FOMC: mone Comparisons & pres Pages</h1>")
    index_parts.append("<h2>Available pages</h2>")
    index_parts.append("<ul>")
    if links:
        # sort links by text so grouping is stable
        for l in sorted(links):
            index_parts.append(l)
    else:
        index_parts.append("<li>No pages generated. Put pred_YYYYMMDDmone.csv and/or pred_YYYYMMDDpres.csv into predicted/txt_pred/</li>")
    index_parts.append("</ul>")
    index_parts.append("</body></html>")

    with open(os.path.join(WEB_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_parts))

    print("Done. Generated pages in:", WEB_DIR)
    print(f" - Comparisons: {COMPARISONS_DIR}")
    print(f" - Pres pages: {PRES_PAGES_DIR}")
    print(f" - Plots copied to: {PLOTS_WEB_DIR}")
    print("Index ->", os.path.join(WEB_DIR, "index.html"))

if __name__ == "__main__":
    main()
