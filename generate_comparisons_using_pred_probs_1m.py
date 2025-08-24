#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_comparisons_using_pred_probs_1m.py (updated)
- Plots 1-min data for FOMC days, plotting window 13:30 ET - 16:00 ET.
- Keeps t0=14:00, t1=14:30, t2=15:00 vertical markers.
- DRAW_COLOR_SEGMENTS toggle remains (default False).
- Reads 1-min CSVs from data/polygon_1m_full/{TICKER}/
- Only processes the allowed TICKERS list (SPY, QQQ, SHY) and ensures
  only those tickers' PNGs are chosen/copied to the web folder.
- Compare pages show 3 PNGs per date (total 6). Pres pages show 3 PNGs for the date.
- Adds "Common" sentences section (colored by stance) on comparison pages;
  common sentences are NOT included in stance-percentage calculations.
- Adds an "About / Legend" page in English and links it from the top of index.html.
- **ADDED**: x-axis annotation "Pres End(mean) 15:30 ET" on each plot PNG.
"""
import os
import re
import glob
import shutil
import csv
import math
import datetime
from collections import OrderedDict
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dateutil import tz


# ---------- CONFIG ----------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

PRED_DIR = os.path.join(PROJECT_ROOT, "predicted", "txt_pred")
PRED_STATEMENT_DIR = os.path.join(PROJECT_ROOT, "predicted", "statement_txt")
PRED_BLOCKS_PRES_DIR = os.path.join(PROJECT_ROOT, "predicted", "blocks_pres_txt")
DATA_1M_ROOT = os.path.join(PROJECT_ROOT, "data", "polygon_1m_full")
RESULTS_PLOTS_DIR = os.path.join(PROJECT_ROOT, "results", "plots")
RESULTS_CSV_DIR = os.path.join(PROJECT_ROOT, "results", "csv")
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
COMPARISONS_DIR = os.path.join(WEB_DIR, "comparisons")
PRES_PAGES_DIR = os.path.join(WEB_DIR, "pres")
PLOTS_WEB_DIR = os.path.join(WEB_DIR, "plots")
STYLE_PATH = os.path.join(WEB_DIR, "style.css")
ABOUT_PAGE = os.path.join(WEB_DIR, "about.html")

# Tickers to generate 1-min plots for (only these 3)
TICKERS = ["SPY", "QQQ", "SHY"]

# CSV timestamp handling: normalize indexes to this timezone
CSV_TIMEZONE = "America/New_York"

# Process only dates >= this (YYYYMMDD)
START_DATE = "20230901"

# Toggle colored segments drawing: DEFAULT = False (OFF)
DRAW_COLOR_SEGMENTS = False

# create directories
os.makedirs(COMPARISONS_DIR, exist_ok=True)
os.makedirs(PRES_PAGES_DIR, exist_ok=True)
os.makedirs(PLOTS_WEB_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)
os.makedirs(RESULTS_PLOTS_DIR, exist_ok=True)
os.makedirs(RESULTS_CSV_DIR, exist_ok=True)

# annotation stats
PLOT_ANNOTATION_STATS = {"total": 0, "green": 0, "red": 0, "skipped": 0}
PLOT_ANNOTATED = set()

PROB_COL_CANDIDATES = ["max_prob", "prob", "probability", "score", "confidence", "maxprob", "pred_prob"]

# ---------- helpers ----------
def escape_html(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&#39;"))

def ensure_style_css(path):
    if os.path.exists(path):
        return
    css = """
body{font-family:Arial,Helvetica,sans-serif;margin:20px}
h1{font-size:1.2rem}
.sent-text{padding:6px;border-radius:4px;display:block;margin:6px 0}
img{max-width:100%}
.plot-grid{display:flex;flex-wrap:wrap;gap:12px}
.plot-grid .plot{flex:1 1 30%;min-width:220px}
.legend-item{display:flex;align-items:center;gap:8px;margin:6px 0}
.legend-swatch{width:18px;height:12px;border-radius:3px;display:inline-block;border:1px solid #444}
"""
    with open(path,"w",encoding="utf-8") as f:
        f.write(css)

def _basename_has_allowed_ticker(bn):
    up = bn.upper()
    for tk in TICKERS:
        if tk.upper() in up:
            return True
    return False

# ---------- pred CSV reader ----------
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
                if pred_raw in ("hawkish","hawk","h","neutral","neural","n","dovish","dove","d"):
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

def hawk_share_from_pred_file(p):
    if not p or not os.path.isfile(p):
        return None
    rows = read_pred_csv(p)
    if not rows:
        return None
    total_prob = sum(r.get("max_prob",0.0) for r in rows)
    hawk_prob = sum(r.get("max_prob",0.0) for r in rows if "hawk" in (r.get("pred_label") or ""))
    if total_prob > 0.0:
        return float(hawk_prob / total_prob)
    cnt = len(rows)
    hawks = sum(1 for r in rows if "hawk" in (r.get("pred_label") or ""))
    return float(hawks / cnt) if cnt>0 else None

# ---------- pred discovery ----------
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
                    for f in found:
                        bn = os.path.basename(f).lower()
                        if kind in bn or 'pred' in bn:
                            return f
                    return found[0]
    return None

def get_pred_paths_for_date(date_hint):
    variants = date_variants_from_string(date_hint) or [date_hint]
    stmt = _search_pred_by_kind_and_date("mone", variants)
    pres = _search_pred_by_kind_and_date("pres", variants)
    return stmt, pres

# ---------- 1-min CSV helpers ----------
def find_1m_csv_for_ticker_and_date(ticker, date_str):
    dir_t = os.path.join(DATA_1M_ROOT, ticker)
    if not os.path.isdir(dir_t):
        return None
    tokens = date_variants_from_string(date_str) or [date_str]
    for t in tokens:
        found = sorted(glob.glob(os.path.join(dir_t, f"*{t}*.csv")) + glob.glob(os.path.join(dir_t, f"*{t}*.txt")))
        if found:
            return found[0]
    if len(date_str) >= 4:
        found = sorted(glob.glob(os.path.join(dir_t, f"*{date_str[:4]}*.csv")))
        if found:
            return found[0]
    return None

def load_1m_close_series(csv_path):
    """
    Robust loader: 여러 포맷(구분자, 날짜칼럼명, 숫자포맷)을 시도해서
    DatetimeIndex (America/New_York) -> Series(close price)를 반환합니다.
    Returns None on failure (and prints debugging info).
    """
    import csv as _csv
    if not csv_path or not os.path.isfile(csv_path):
        return None
    try:
        size = os.path.getsize(csv_path)
        if size == 0:
            print(f"[load_1m_close_series] Empty file: {csv_path}")
            return None

        # sniff delimiter from sample
        delim = ","
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as tf:
                sample = tf.read(8192)
            try:
                sniff = _csv.Sniffer().sniff(sample)
                delim = sniff.delimiter
            except Exception:
                for d in [',',';','\t','|']:
                    if d in sample:
                        delim = d
                        break
        except Exception as e:
            print(f"[load_1m_close_series] Sniff failed: {e}")

        # read small sample to inspect columns (use python engine to allow flexible sep)
        try:
            sample_df = pd.read_csv(csv_path, nrows=50, sep=delim, encoding='utf-8', engine='python')
        except Exception:
            try:
                sample_df = pd.read_csv(csv_path, nrows=50, sep=delim, encoding='latin1', engine='python')
            except Exception as e2:
                print(f"[load_1m_close_series] Failed to read sample from {csv_path}: {e2}")
                return None

        cols = list(sample_df.columns)
        time_candidates = [c for c in cols if re.search(r'date|time|datetime|timestamp|ts', c, re.I)]
        close_candidates = [c for c in cols if re.search(r'^(close|adjclose|adj close|adjusted close|price|last|px_close|close_price)$', c, re.I)]
        if not close_candidates:
            numcols = [c for c in cols if pd.api.types.is_numeric_dtype(sample_df[c])]
            if numcols:
                close_candidates = [numcols[-1]]

        if not time_candidates:
            for c in cols:
                s = sample_df[c].astype(str).head(10).tolist()
                parsed = 0
                for v in s:
                    try:
                        pd.to_datetime(v)
                        parsed += 1
                    except:
                        pass
                if parsed >= 5:
                    time_candidates.append(c)
                    break

        if not time_candidates:
            print(f"[load_1m_close_series] No obvious time column in {csv_path}. COLUMNS: {cols}")
            tcol = cols[0]
        else:
            tcol = time_candidates[0]

        if not close_candidates:
            print(f"[load_1m_close_series] No obvious close/price column in {csv_path}. COLUMNS: {cols}")
            return None
        else:
            ccol = close_candidates[0]

        # 3) read full CSV: try fast C engine first (with low_memory), fallback to python engine (without low_memory)
        try:
            df = pd.read_csv(csv_path, low_memory=False, sep=delim, encoding='utf-8')
        except Exception:
            try:
                # fallback to python engine but DO NOT pass low_memory (unsupported)
                df = pd.read_csv(csv_path, sep=delim, encoding='utf-8', engine='python')
            except Exception:
                try:
                    df = pd.read_csv(csv_path, sep=delim, encoding='latin1', engine='python')
                except Exception as e:
                    print(f"[load_1m_close_series] Failed to read full CSV {csv_path}: {e}")
                    return None

        # case-insensitive column match
        if tcol not in df.columns:
            for c in df.columns:
                if c.strip().lower() == tcol.strip().lower():
                    tcol = c
                    break
        if ccol not in df.columns:
            for c in df.columns:
                if c.strip().lower() == ccol.strip().lower():
                    ccol = c
                    break

        # coerce numeric on ccol (remove $ ,)
        try:
            df[ccol] = df[ccol].astype(str).str.replace(r'[\$,]', '', regex=True)
            df[ccol] = pd.to_numeric(df[ccol], errors='coerce')
        except Exception:
            numcols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            if numcols:
                ccol = numcols[-1]
            else:
                print(f"[load_1m_close_series] No numeric column found in {csv_path}. Columns: {list(df.columns)}")
                return None

        # parse datetimes robustly
        try:
            df[tcol] = pd.to_datetime(df[tcol], errors='coerce', utc=False)
            if df[tcol].isna().sum() > len(df)*0.5:
                try:
                    df[tcol] = pd.to_datetime(df[tcol].astype(str), errors='coerce', utc=True)
                except:
                    pass
        except Exception:
            try:
                df[tcol] = pd.to_datetime(df[tcol].astype(str), errors='coerce')
            except Exception as e:
                print(f"[load_1m_close_series] datetime parse failed for {csv_path}: {e}")
                return None

        df = df[[tcol, ccol]].dropna(subset=[tcol, ccol])
        if df.empty:
            print(f"[load_1m_close_series] No valid rows after parsing time/price for {csv_path}")
            return None

        ser = df.set_index(tcol)[ccol].copy()
        ser.index = pd.DatetimeIndex(ser.index)
        ser = ser.sort_index().dropna()

        # timezone handling: prefer CSV_TIMEZONE if provided
        try:
            if 'CSV_TIMEZONE' in globals() and CSV_TIMEZONE:
                if ser.index.tz is None:
                    try:
                        ser.index = ser.index.tz_localize(CSV_TIMEZONE)
                    except Exception:
                        try:
                            ser.index = ser.index.tz_localize('UTC').tz_convert(CSV_TIMEZONE)
                        except:
                            pass
                else:
                    try:
                        ser.index = ser.index.tz_convert(CSV_TIMEZONE)
                    except:
                        pass
            else:
                if ser.index.tz is None:
                    try:
                        ser.index = ser.index.tz_localize('UTC').tz_convert('America/New_York')
                    except:
                        try:
                            ser.index = ser.index.tz_localize('America/New_York')
                        except:
                            pass
                else:
                    try:
                        ser.index = ser.index.tz_convert('America/New_York')
                    except:
                        pass
        except Exception:
            pass

        return ser
    except Exception as e:
        print(f"[load_1m_close_series] Unexpected error reading {csv_path}: {e}")
        return None


# ---------- create 1-min plot (FOMC window 13:30-16:00) ----------
def create_1min_plot_for_ticker_date(ticker, date_str, out_dir=RESULTS_PLOTS_DIR, mone_path=None, pres_path=None, agg_minutes=1):
    # safety check
    if ticker.upper() not in [t.upper() for t in TICKERS]:
        print(f"[create_plot] Skipping ticker not allowed: {ticker}")
        return None

    csv_1m = find_1m_csv_for_ticker_and_date(ticker, date_str)
    if not csv_1m:
        print(f"[create_plot] No 1m CSV for {ticker} {date_str}")
        return None
    ser = load_1m_close_series(csv_1m)
    if ser is None or ser.empty:
        print(f"[create_plot] Couldn't load series for {csv_1m}")
        return None

    # restrict to US regular hours (we'll further subset to 13:30-16:00)
    try:
        ser_rt = ser.between_time('09:30', '16:00')
    except Exception:
        ser_rt = ser

    if ser_rt.empty:
        print(f"[create_plot] No regular-hours data for {ticker} {date_str} -> SKIP")
        PLOT_ANNOTATION_STATS["skipped"] += 1
        return None

    if agg_minutes > 1:
        ser_rt = ser_rt.resample(f"{agg_minutes}T").last().dropna()

    # parse date to construct target timestamps
    d = None
    try:
        if '-' in date_str:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        else:
            d = datetime.datetime.strptime(date_str, "%Y%m%d")
    except Exception:
        m = re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})', date_str)
        if m:
            d = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if d is None:
        print(f"[create_plot] Could not parse date {date_str}")
        return None

    # FOMC event markers
    t0 = pd.Timestamp(datetime.datetime(d.year, d.month, d.day, 14, 0), tz='America/New_York')
    t1 = pd.Timestamp(datetime.datetime(d.year, d.month, d.day, 14, 30), tz='America/New_York')
    t2 = pd.Timestamp(datetime.datetime(d.year, d.month, d.day, 15, 0), tz='America/New_York')
    # NEW: Pres end (mean) marker at 15:30 ET
    t3 = pd.Timestamp(datetime.datetime(d.year, d.month, d.day, 15, 30), tz='America/New_York')

    # plotting window from 13:30 to 16:00
    window_start = pd.Timestamp(datetime.datetime(d.year, d.month, d.day, 13, 30), tz='America/New_York')
    window_end   = pd.Timestamp(datetime.datetime(d.year, d.month, d.day, 16, 0), tz='America/New_York')

    # nearest close helper
    def nearest_close(ts, series):
        if ts in series.index:
            return ts, float(series.loc[ts])
        if series.index.empty:
            return None, None
        diffs = np.array([abs((idx - ts).total_seconds()) for idx in series.index])
        idx_min = int(diffs.argmin())
        nearest = series.index[idx_min]
        if diffs[idx_min] <= 5*60:
            return nearest, float(series.iloc[idx_min])
        return None, None

    t0a, c0 = nearest_close(t0, ser_rt)
    t1a, c1 = nearest_close(t1, ser_rt)
    t2a, c2 = nearest_close(t2, ser_rt)

    # restrict to window
    ser_window = ser_rt.loc[(ser_rt.index >= window_start) & (ser_rt.index <= window_end)]
    if ser_window.empty:
        print(f"[create_plot] No data in 13:30-16:00 window for {ticker} {date_str} -> SKIP")
        PLOT_ANNOTATION_STATS["skipped"] += 1
        return None

    # compute hawk-shares (may be None)
    stmt_path, pres_path = get_pred_paths_for_date(date_str)
    stmt_score = hawk_share_from_pred_file(stmt_path) if stmt_path else None
    press_score = hawk_share_from_pred_file(pres_path) if pres_path else None

    # output filename
    ytok = d.strftime("%Y%m%d")
    out_png = os.path.join(out_dir, f"{ticker}_1m_{ytok}_with_sentiment.png")

    # create plot
    fig, ax = plt.subplots(figsize=(12,6))
    ax.plot(ser_window.index, ser_window.values, linewidth=1, zorder=1)
    ax.set_title(f"{ticker} 1-min on {d.strftime('%Y-%m-%d')} (13:30-16:00 ET)")
    ax.set_xlabel("Time (America/New_York)")
    ax.set_ylabel("Price")

    # x-axis formatter using NY tz
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz.gettz("America/New_York")))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0,15,30,45]))
    ax.grid(True, alpha=0.25)

    # vertical markers (statement and press conf)
    for ts, label in ((t0, "Statement 14:00 ET"), (t1, "Press Conf 14:30 ET")):
        ax.axvline(ts, linestyle='--', linewidth=1, zorder=2)
        ylim = ax.get_ylim()
        ax.text(ts, ylim[1], label, va='bottom', ha='left', rotation=90, fontsize=9)

    # NEW: add Pres End(mean) 15:30 ET marker (same style/placement as other vertical labels)
    ax.axvline(t3, linestyle='--', linewidth=1, zorder=2, color='black')
    ylim = ax.get_ylim()
    ax.text(t3, ylim[1], "PRES END (mean)", va='bottom', ha='left', rotation=90, fontsize=9)

    # intervals for optional colored segments
    intervals = []
    if t0a is not None and t1a is not None:
        intervals.append(("half1", t0a, c0, t1a, c1))
    if t1a is not None and t2a is not None:
        intervals.append(("half2", t1a, c1, t2a, c2))

    found_green = False
    if DRAW_COLOR_SEGMENTS:
        for name, ta, ca, tb, cb in intervals:
            change = cb - ca
            color = 'grey'
            reason = 'missing_score'
            if (stmt_score is not None) and (press_score is not None):
                if (change < 0 and press_score > stmt_score) or (change > 0 and press_score < stmt_score):
                    color = 'green'; reason = 'match'
                else:
                    color = 'red'; reason = 'mismatch'
            else:
                color = 'grey'; reason = 'no_scores'
            ax.plot([ta, tb], [ca, cb], linewidth=6, color=color, solid_capstyle='round', zorder=5)
            ax.axvspan(min(ta,tb), max(ta,tb), ymin=0.02, ymax=0.12, facecolor=color, alpha=0.18, zorder=0)
            midt = ta + (tb - ta) / 2
            midy = (ca + cb) / 2
            ax.text(midt, midy, f"{name.upper()} {color.upper()}", ha='center', va='bottom', fontsize=9, fontweight='bold', color=color)
            print(f"[plot] {ticker} {d.strftime('%Y-%m-%d')} {name}: {ta.strftime('%H:%M')}->{tb.strftime('%H:%M')} change={change:.6f} stmt={stmt_score} press={press_score} => {color} ({reason})")
            if (stmt_score is not None) and (press_score is not None) and ((change < 0 and press_score > stmt_score) or (change > 0 and press_score < stmt_score)):
                found_green = True
    else:
        print(f"[plot] color segments disabled (DRAW_COLOR_SEGMENTS=False) for {ticker} {date_str}. Intervals: {[(n, ta, tb) for (n,ta,ca,tb,cb) in intervals]}")

    # small label percentages table (if pred files exist)
    def read_label_percents(path):
        if not path or not os.path.isfile(path):
            return None
        try:
            df = pd.read_csv(path, encoding='utf-8', low_memory=False)
        except Exception:
            return None
        labcol = None
        for c in df.columns:
            if c.lower() in ('pred_label','predlabel','label','pred'):
                labcol = c; break
        if labcol is None:
            for c in df.columns:
                s = df[c].astype(str).str.lower().head(30).tolist()
                if any(('dov' in x or 'hawk' in x or 'neutral' in x) for x in s):
                    labcol = c; break
        if labcol is None:
            return None
        labels = df[labcol].astype(str).str.lower()
        total = len(labels)
        if total == 0:
            return None
        dov = labels.str.contains('dov').sum()
        hawk = labels.str.contains('hawk').sum()
        neut = labels.str.contains('neu').sum()
        return (dov/total*100.0, hawk/total*100.0, neut/total*100.0)

    stmt_percs = read_label_percents(mone_path) if mone_path else None
    pres_percs = read_label_percents(pres_path) if pres_path else None
    if stmt_percs or pres_percs:
        header = ["Category","Dovish(%)","Hawkish(%)","Neutral(%)"]
        stmt_row = ["Statement",
                    f"{stmt_percs[0]:.2f}" if stmt_percs else "N/A",
                    f"{stmt_percs[1]:.2f}" if stmt_percs else "N/A",
                    f"{stmt_percs[2]:.2f}" if stmt_percs else "N/A"]
        pres_row = ["Press Conf.",
                   f"{pres_percs[0]:.2f}" if pres_percs else "N/A",
                   f"{pres_percs[1]:.2f}" if pres_percs else "N/A",
                   f"{pres_percs[2]:.2f}" if pres_percs else "N/A"]
        table = ax.table(cellText=[header, stmt_row, pres_row],
                         cellLoc='center', loc='upper left', bbox=[0.01,0.72,0.38,0.22])
        table.auto_set_font_size(False); table.set_fontsize(9); table.scale(1.02,1.02)

    ax.set_xlim(window_start, window_end)

    plt.tight_layout()
    try:
        fig.savefig(out_png, dpi=150)
    except Exception as e:
        print(f"[create_plot] Failed to save {out_png}: {e}")
        plt.close(fig)
        return None
    plt.close(fig)

    # copy to web plots dir only if filename is allowed
    try:
        basename = os.path.basename(out_png)
        if _basename_has_allowed_ticker(basename):
            dst = os.path.join(PLOTS_WEB_DIR, basename)
            shutil.copy2(out_png, dst)
    except Exception:
        pass

    PLOT_ANNOTATION_STATS["total"] += 1
    if DRAW_COLOR_SEGMENTS:
        if found_green:
            PLOT_ANNOTATION_STATS["green"] += 1
        else:
            PLOT_ANNOTATION_STATS["red"] += 1
    else:
        PLOT_ANNOTATION_STATS["skipped"] += 1

    PLOT_ANNOTATED.add(os.path.basename(out_png))
    return out_png

# ---------- create/find plots for date ----------
def create_1min_plots_for_date(date_str):
    """
    Create 1-min plots for all TICKERS for the given date.
    Returns list of created filepaths (may be empty).
    """
    created = []
    stmt_path, pres_path = get_pred_paths_for_date(date_str)
    for tk in TICKERS:
        out_png = create_1min_plot_for_ticker_date(tk, date_str, out_dir=RESULTS_PLOTS_DIR, mone_path=stmt_path, pres_path=pres_path, agg_minutes=1)
        if out_png:
            created.append(out_png)
    return created

def find_plots_for_date(date_str):
    """
    결과 디렉터리(RESULTS_PLOTS_DIR)에서 허용된 TICKERS의 plot 파일들을 모두 찾아반환.
    파일이 없으면 create_1min_plots_for_date로 생성 시도 후 다시 검색.
    Returns list of full paths (may be empty).
    """
    found = []
    variants = date_variants_from_string(date_str) or [date_str]
    exts = ["png","jpg","jpeg"]
    for tk in TICKERS:
        matched = None
        for v in variants:
            for ext in exts:
                pat = os.path.join(RESULTS_PLOTS_DIR, f"*{tk}*{v}*.{ext}")
                got = sorted(glob.glob(pat))
                if got:
                    matched = got[0]
                    break
            if matched:
                break
        if matched:
            found.append(matched)
    if not found:
        # try to create them
        create_1min_plots_for_date(date_str)
        # search again
        for tk in TICKERS:
            for v in variants:
                for ext in exts:
                    pat = os.path.join(RESULTS_PLOTS_DIR, f"*{tk}*{v}*.{ext}")
                    got = sorted(glob.glob(pat))
                    if got:
                        found.append(got[0])
                        break
                if any(f for f in found if tk.upper() in os.path.basename(f).upper()):
                    break
    # ensure unique and return
    unique = []
    for p in found:
        if p not in unique and _basename_has_allowed_ticker(os.path.basename(p)):
            unique.append(p)
    return unique

def collect_plot_rels_for_date(date_str):
    """
    find_plots_for_date로 찾은 파일들을 웹 상대경로로 복사(annotate_and_copy_plot)하고
    'plots/<basename>' 리스트를 반환.
    """
    fps = find_plots_for_date(date_str)
    rels = []
    for fp in fps:
        rel = annotate_and_copy_plot(fp, date_str)
        if rel:
            rels.append(rel)
    return rels

def annotate_and_copy_plot(plot_src, date_hint, search_kind=None):
    """
    웹으로 복사할 때 허용된 티커인지 확인하여 복사.
    Returns relative path 'plots/<basename>' or None.
    """
    if not plot_src or not os.path.isfile(plot_src):
        return None
    basename = os.path.basename(plot_src)
    if not _basename_has_allowed_ticker(basename):
        print(f"[annotate] Skipping copy of non-allowed ticker plot: {basename}")
        return None
    dst = os.path.join(PLOTS_WEB_DIR, basename)
    try:
        if (not os.path.exists(dst)) or (os.path.getmtime(plot_src) > os.path.getmtime(dst)):
            shutil.copy2(plot_src, dst)
    except Exception as e:
        print(f"[annotate] Warning copying plot: {e}")
        return None
    # increment tracked total (this counts plots made available on web)
    PLOT_ANNOTATION_STATS["total"] += 1
    PLOT_ANNOTATED.add(basename)
    return f"plots/{basename}"

# ---------- simple HTML generators ----------
def generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot_rels, new_plot_rels):
    """
    old_plot_rels and new_plot_rels are lists of 'plots/<basename>' relative paths.
    We will display each date's plots in a grid (3 per date expected).
    Also add a 'Common' section (sentences present in both old_map and new_map),
    colored by stance. Common sentences are NOT included in added/removed lists
    (and therefore not reflected in stance percentages).
    """
    title = f"Compare {old_date} → {new_date} (mone)"
    parts = [f"<h1>{escape_html(title)}</h1>"]

    # helper to render a set of images for one date
    def render_plots_block(label, rels):
        out = [f"<h3>{escape_html(label)}</h3>"]
        if rels:
            out.append("<div class='plot-grid'>")
            for r in rels:
                out.append(f"<div class='plot'><img src='../{escape_html(r)}' alt='{escape_html(r)}'></div>")
            out.append("</div>")
        else:
            out.append("<p><em>No plots available.</em></p>")
        return "\n".join(out)

    parts.append("<div style='display:flex;gap:20px;align-items:flex-start'>")
    parts.append(f"<div style='flex:1'>{render_plots_block(old_date, old_plot_rels)}</div>")
    parts.append(f"<div style='flex:1'>{render_plots_block(new_date, new_plot_rels)}</div>")
    parts.append("</div>")

    # find common sentences (present in both maps)
    common_keys = [k for k in old_map.keys() if k in new_map]
    # color helper for sentences (prefer new_map label, else old_map)
    def _color_for_from_maps(k):
        if k in new_map and new_map[k].get("label"):
            lab = new_map[k].get("label", "neutral")
        else:
            lab = old_map.get(k, {}).get("label", "neutral")
        lab = (lab or "neutral").lower()
        return {"hawkish": "red", "dovish": "green", "neutral": "gray"}.get(lab, "black")

    # COMMON section (colored by stance). These are shown but NOT counted in added/removed.
    parts.append("<h2>Common</h2>")
    if common_keys:
        for k in common_keys:
            color = _color_for_from_maps(k)
            # show both probs if available (old/new) for information only
            old_p = old_map.get(k, {}).get("max_prob")
            new_p = new_map.get(k, {}).get("max_prob")
            prob_text = ""
            if old_p is not None and new_p is not None:
                prob_text = f" <small>(old:{old_p:.3f} new:{new_p:.3f})</small>"
            elif new_p is not None:
                prob_text = f" <small>(new:{new_p:.3f})</small>"
            elif old_p is not None:
                prob_text = f" <small>(old:{old_p:.3f})</small>"
            parts.append(f'<p class="sent-text" style="color:{color}">{escape_html(k)}{prob_text}</p>')
    else:
        parts.append("<p><em>None</em></p>")

    # color helper for sentences (single-map arg)
    def _color_for(m):
        lab = (m.get("label") or "neutral").lower()
        return {"hawkish": "red", "dovish": "green", "neutral": "gray"}.get(lab, "black")

    # Added/Removed excluding common (common already removed above)
    added = {t: new_map[t] for t in new_map if t not in old_map}
    removed = {t: old_map[t] for t in old_map if t not in new_map}

    parts.append("<h2>Added</h2>")
    if added:
        for t, m in added.items():
            color = _color_for(m)
            parts.append(f'<p class="sent-text" style="color:{color}">{escape_html(t)} <small>({m.get("max_prob",0.0):.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")

    parts.append("<h2>Removed</h2>")
    if removed:
        for t, m in removed.items():
            color = _color_for(m)
            parts.append(f'<p class="sent-text"><del style="color:{color}">{escape_html(t)}</del> <small>({m.get("max_prob",0.0):.3f})</small></p>')
    else:
        parts.append("<p><em>None</em></p>")

    parts.append('<p><a href="../index.html">&larr; Back</a></p>')
    return "\n".join(parts)

def generate_pres_page_html(pres_map, date_str, plot_rels):
    title = f"Pres {date_str}"
    parts = [f"<h1>{escape_html(title)}</h1>"]
    # show plots (expected 3)
    parts.append("<h2>Plots</h2>")
    if plot_rels:
        parts.append("<div class='plot-grid'>")
        for r in plot_rels:
            parts.append(f"<div class='plot'><img src='../{escape_html(r)}' alt='{escape_html(r)}'></div>")
        parts.append("</div>")
    else:
        parts.append("<p><em>No plots available.</em></p>")

    parts.append("<h2>Sentences</h2>")

    def _color_for(m):
        lab = (m.get("label") or "neutral").lower()
        return {"hawkish": "red", "dovish": "green", "neutral": "gray"}.get(lab, "black")

    if pres_map:
        for t, m in pres_map.items():
            color = _color_for(m)
            parts.append(f'<p class="sent-text" style="color:{color}">{escape_html(t)} <small>({m.get("max_prob",0.0):.3f})</small></p>')
    else:
        parts.append("<p><em>No sentences found.</em></p>")

    parts.append('<p><a href="../index.html">&larr; Back</a></p>')
    return "\n".join(parts)

def generate_about_page_html():
    """
    English explanation page: FOMC press conference durations and legend for
    stance colors and confidence numbers.
    """
    parts = []
    parts.append("<h1>About FOMC Press Conferences & Legend</h1>")
    parts.append("<p><strong>Typical duration</strong>: The average length of an FOMC press conference is roughly <strong>54–55 minutes</strong>.")
    parts.append("For example, one analysis of 41 press conferences between April 2011 and January 2020 reported a mean duration of <strong>54 minutes 47 seconds</strong>.</p>")
    parts.append("<p><strong>Typical breakdown</strong>: The Chair's opening statement is usually about <strong>~10 minutes</strong>, and the remainder (~44–45 minutes) is taken up by the Q&amp;A session with reporters.</p>")
    parts.append("<h2>Legend — stance colors</h2>")
    parts.append("<div class='legend-item'><span class='legend-swatch' style='background:red'></span> <strong>Red (Hawkish)</strong>: language suggesting tightening or higher-for-longer policy. We mark sentences labeled <em>hawkish</em> in red.</div>")
    parts.append("<div class='legend-item'><span class='legend-swatch' style='background:green'></span> <strong>Green (Dovish)</strong>: language suggesting easing or more accommodation. We mark sentences labeled <em>dovish</em> in green.</div>")
    parts.append("<div class='legend-item'><span class='legend-swatch' style='background:gray'></span> <strong>Gray (Neutral)</strong>: neutral / mixed language. We mark sentences labeled <em>neutral</em> in gray.</div>")
    parts.append("<h2>Confidence / probability numbers</h2>")
    parts.append("<p>Each sentence listed on the pages includes a numeric <strong>confidence</strong> value produced by the model. It is shown as a decimal between <strong>0.00</strong> and <strong>1.00</strong> (three decimal places in the UI). Higher values indicate stronger model confidence in the assigned label.</p>")
    parts.append("<h2>Common sentences</h2>")
    parts.append("<p>On comparison pages, sentences that appear in <em>both</em> dates are listed under the <strong>Common</strong> section and colored by stance. These common sentences are <em>not</em> counted in the 'added'/'removed' stance percentage calculations.</p>")
    parts.append('<p><a href="index.html">&larr; Back to index</a></p>')
    return "\n".join(parts)

# ---------- dedupe scan ----------
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
    # generate about page
    about_html = generate_about_page_html()
    try:
        with open(ABOUT_PAGE, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>About / Legend</title><link rel='stylesheet' href='style.css'></head><body>\n")
            f.write(about_html)
            f.write("\n</body></html>")
    except Exception as e:
        print(f"[main] Warning writing about page: {e}")

    mone_by_date, pres_by_date = scan_predicted_files()
    mone_dates = sorted(mone_by_date.keys())
    pres_dates = sorted(pres_by_date.keys())

    def filter_by_start(dates, start):
        if not start:
            return dates
        out = [d for d in dates if (len(d) >= 8 and d >= start) or (len(d) < 8 and d >= start)]
        return out

    mone_dates = filter_by_start(mone_dates, START_DATE)
    pres_dates = filter_by_start(pres_dates, START_DATE)

    print("Processing only dates >= START_DATE:", START_DATE)
    print("Found (after filter) mone dates:", mone_dates)
    print("Found (after filter) pres dates:", pres_dates)
    print("DRAW_COLOR_SEGMENTS =", DRAW_COLOR_SEGMENTS)
    links = []

    # comparisons (pairwise adjacent mone dates)
    for i in range(1, len(mone_dates)):
        old_date = mone_dates[i-1]; new_date = mone_dates[i]

        # create plots for old_date/new_date (only TICKERS)
        create_1min_plots_for_date(old_date)
        create_1min_plots_for_date(new_date)

        # collect plots (3 per date expected)
        old_plot_rels = collect_plot_rels_for_date(old_date)
        new_plot_rels = collect_plot_rels_for_date(new_date)

        if not old_plot_rels and not new_plot_rels:
            print(f"[skip compare] {old_date} -> {new_date}: missing plots for tickers -> skipping")
            continue

        old_fp = mone_by_date.get(old_date); new_fp = mone_by_date.get(new_date)
        print(f"[compare] {old_date} -> {new_date} (files: {os.path.basename(old_fp) if old_fp else 'N/A'} , {os.path.basename(new_fp) if new_fp else 'N/A'})")
        old_data = read_pred_csv(old_fp) if old_fp else []
        new_data = read_pred_csv(new_fp) if new_fp else []
        old_map = make_text_map_with_prob(old_data); new_map = make_text_map_with_prob(new_data)

        html = generate_mone_comparison_html(old_map, new_map, old_date, new_date, old_plot_rels, new_plot_rels)
        out_name = f"compare_{old_date}_to_{new_date}_mone.html"; out_path = os.path.join(COMPARISONS_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>"+escape_html(f"Compare {old_date}->{new_date}")+"</title><link rel='stylesheet' href='../style.css'></head><body>\n")
            f.write(html); f.write("\n</body></html>")
        links.append((f"{old_date} → {new_date} (mone)", f"comparisons/{out_name}"))

    # pres pages (single-date pages showing 3 plots + sentences)
    for date in pres_dates:
        pres_fp = pres_by_date.get(date)
        # ensure plots exist/create
        create_1min_plots_for_date(date)
        plot_rels = collect_plot_rels_for_date(date)
        if not plot_rels:
            print(f"[skip pres] {date}: missing plots for tickers -> skipping")
            continue
        print(f"[pres page] {date} (file: {os.path.basename(pres_fp) if pres_fp else 'N/A'})")
        pres_data = read_pred_csv(pres_fp) if pres_fp else []
        pres_map = make_text_map_with_prob(pres_data)
        html = generate_pres_page_html(pres_map, date, plot_rels)
        out_name = f"pres_{date}.html"; out_path = os.path.join(PRES_PAGES_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>"+escape_html(f"Pres {date}")+"</title><link rel='stylesheet' href='../style.css'></head><body>\n")
            f.write(html); f.write("\n</body></html>")
        links.append((f"Pres {date}", f"pres/{out_name}"))

    # index
    index_html = ["<!DOCTYPE html><html><head><meta charset='utf-8'><title>Index</title><link rel='stylesheet' href='style.css'></head><body>"]
    # add about link at top
    index_html.append('<p><a href="about.html">About FOMC press conferences & legend (English)</a></p>')
    index_html.append("<h1>FOMC: mone Comparisons & pres Pages (1m 13:30-16:00 ET plots)</h1>")
    if links:
        index_html.append("<ul>")
        for title,href in sorted(links):
            index_html.append(f"<li><a href='{href}'>{escape_html(title)}</a></li>")
        index_html.append("</ul>")
    else:
        index_html.append("<p>No pages generated. Place predicted files and 1-min CSVs under data/polygon_1m_full/{TICKER}/</p>")
    index_html.append("</body></html>")
    with open(os.path.join(WEB_DIR,"index.html"),"w",encoding="utf-8") as f:
        f.write("\n".join(index_html))

    print("Index ->", os.path.join(WEB_DIR,"index.html"))
    tot = PLOT_ANNOTATION_STATS.get("total",0); g = PLOT_ANNOTATION_STATS.get("green",0); r = PLOT_ANNOTATION_STATS.get("red",0); s = PLOT_ANNOTATION_STATS.get("skipped",0)
    if tot:
        print(f"Plot annotation summary: total={tot}, green={g} ({100.0*g/tot:.1f}%), red={r} ({100.0*r/tot:.1f}%), skipped={s}")
    else:
        print(f"Plot annotation summary: total=0, skipped={s}")

if __name__ == "__main__":
    main()
