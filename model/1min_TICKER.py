#!/usr/bin/env python3
# local_1min_TICKER.py (updated: split hour into two half-hours and compare)
import argparse, os, glob, re
from datetime import datetime, time, timedelta
import pytz
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

NY = pytz.timezone("America/New_York")

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)

def find_csvs_for_date(data_dir, date_token):
    out = []
    if not os.path.isdir(data_dir):
        return out
    tokens = [date_token, date_token.replace("-", "")]
    for t in tokens:
        patterns = [os.path.join(data_dir, f"*{t}*.csv"), os.path.join(data_dir, f"*{t}*.txt")]
        for pat in patterns:
            for f in sorted(glob.glob(pat)):
                if f not in out:
                    out.append(f)
    return out

def guess_datetime_column(df):
    candidates = [c for c in df.columns if re.search(r'date|time|timestamp|datetime', c, re.I)]
    if candidates:
        return candidates[0]
    return df.columns[0] if len(df.columns)>0 else None

def read_and_concat_csvs(paths):
    dfs=[]
    for p in paths:
        try:
            sample = pd.read_csv(p, nrows=5)
        except Exception as e:
            print(f"  [WARN] cannot read sample {p}: {e}")
            continue
        time_col = guess_datetime_column(sample)
        try:
            df = pd.read_csv(p, parse_dates=[time_col], infer_datetime_format=True)
        except Exception:
            df = pd.read_csv(p)
            try:
                df[time_col] = pd.to_datetime(df[time_col])
            except Exception as e:
                print(f"  [WARN] failed to parse datetime in {p}: {e}")
                continue
        df = df.set_index(time_col)
        if df.index.tz is None:
            try:
                df.index = df.index.tz_localize(pytz.UTC).tz_convert(NY)
            except Exception:
                df.index = df.index.tz_localize(NY)
        else:
            try:
                df.index = df.index.tz_convert(NY)
            except Exception:
                pass
        dfs.append(df)
    if not dfs:
        return None
    combined = pd.concat(dfs).sort_index()
    combined = combined[~combined.index.duplicated(keep='first')]
    return combined

def resample_ohlcv(df, interval):
    cols = {c.lower(): c for c in df.columns}
    mapping = {}
    for k in ['open','high','low','close','volume']:
        if k in cols:
            mapping[cols[k]] = k.capitalize()
    if mapping:
        df = df.rename(columns=mapping)
    if 'Close' not in df.columns:
        numeric_cols = [c for c in df.columns if np.issubdtype(df[c].dtype, np.number)]
        if numeric_cols:
            df['Close'] = df[numeric_cols[-1]]
        else:
            raise RuntimeError("No numeric column for Close found.")
    agg = {}
    if 'Open' in df.columns: agg['Open']='first'
    if 'High' in df.columns: agg['High']='max'
    if 'Low' in df.columns: agg['Low']='min'
    agg['Close']='last'
    if 'Volume' in df.columns: agg['Volume']='sum'
    df_res = df.resample(interval).agg(agg).dropna(how='all')
    return df_res

def read_pred_ratios(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        df = pd.read_csv(path, encoding='utf-8')
    except Exception:
        try:
            df = pd.read_csv(path, encoding='latin-1')
        except Exception as e:
            print(f"  [WARN] cannot read pred csv {path}: {e}")
            return None
    col = None
    for c in df.columns:
        if c.lower() in ('pred_label','predlabel','label','pred'):
            col = c; break
    if col is None:
        for c in df.columns:
            sample = df[c].astype(str).str.lower().head(30).tolist()
            if any('dov' in s or 'hawk' in s or 'neutral' in s for s in sample):
                col = c; break
    if col is None:
        return None
    labels = df[col].astype(str).str.lower().str.strip()
    total = len(labels)
    if total == 0:
        return None
    dov = labels.str.contains('dov').sum()
    hawk = labels.str.contains('hawk').sum()
    neut = labels.str.contains('neu').sum()
    return {'dovish_pct': dov/total*100.0, 'hawkish_pct': hawk/total*100.0, 'neutral_pct': neut/total*100.0, 'total': total}

def get_close_at_or_nearest(df, target_dt, tol_minutes=3):
    """Return (timestamp, close) for the row whose index equals target_dt or nearest within tolerance (minutes)."""
    if target_dt in df.index:
        return target_dt, float(df.loc[target_dt]['Close'])
    # find nearest index
    diffs = (df.index - target_dt).abs()
    if len(diffs)==0:
        return None
    idx_min = diffs.argmin()
    nearest = df.index[idx_min]
    if abs((nearest - target_dt).total_seconds()) <= tol_minutes*60:
        return nearest, float(df.loc[nearest]['Close'])
    return None

def get_half_hour_points(df, date_str):
    """
    Try to get closes at 14:00, 14:30 and 15:00 ET for given date (date_str "YYYY-MM-DD").
    Returns dict with keys 't0','c0' (14:00), 't1','c1' (14:30), 't2','c2' (15:00) where present.
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")
    t0 = NY.localize(datetime(d.year, d.month, d.day, 14, 0))
    t1 = NY.localize(datetime(d.year, d.month, d.day, 14, 30))
    t2 = NY.localize(datetime(d.year, d.month, d.day, 15, 0))
    out = {}
    for name, dt in (('t0',t0),('t1',t1),('t2',t2)):
        got = get_close_at_or_nearest(df, dt, tol_minutes=5)
        if got:
            out[name] = got[0]; out[name.replace('t','c')] = got[1]
        else:
            out[name] = None; out[name.replace('t','c')] = None
    return out

def plot_and_save(df_res, ticker, date_str, interval, out_csv_path, out_png_path, stmt_dt=None, pc_dt=None, mone_csv=None, pres_csv=None, H_THRESH=0.50):
    df_res.to_csv(out_csv_path)
    fig, ax = plt.subplots(figsize=(12,6))
    ax.plot(df_res.index, df_res['Close'], linewidth=1)
    ax.set_title(f"{ticker} {interval} bars on {date_str} (ET)")
    ax.set_xlabel("Time (America/New_York)")
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=NY))
    ax.grid(True, alpha=0.25)
    ytop = ax.get_ylim()[1]

    if stmt_dt is not None:
        ax.axvline(stmt_dt, linestyle="--", linewidth=1)
        ax.text(stmt_dt, ytop, f"Statement {stmt_dt.strftime('%H:%M')}", va="bottom", ha="left", rotation=90)
    if pc_dt is not None:
        ax.axvline(pc_dt, linestyle="--", linewidth=1)
        ax.text(pc_dt, ytop, f"Press Conf {pc_dt.strftime('%H:%M')}", va="bottom", ha="left", rotation=90)

    mone_rat = read_pred_ratios(mone_csv) if mone_csv else None
    pres_rat = read_pred_ratios(pres_csv) if pres_csv else None
    if mone_rat or pres_rat:
        header = ["Category","Dovish (%)","Hawkish (%)","Neutral (%)"]
        stmt_row = ["Statement", f"{mone_rat['dovish_pct']:.2f}" if mone_rat else "N/A",
                    f"{mone_rat['hawkish_pct']:.2f}" if mone_rat else "N/A",
                    f"{mone_rat['neutral_pct']:.2f}" if mone_rat else "N/A"]
        pres_row = ["Press Conf.", f"{pres_rat['dovish_pct']:.2f}" if pres_rat else "N/A",
                    f"{pres_rat['hawkish_pct']:.2f}" if pres_rat else "N/A",
                    f"{pres_rat['neutral_pct']:.2f}" if pres_rat else "N/A"]
        cell_text = [header, stmt_row, pres_row]
        tab = ax.table(cellText=cell_text, cellLoc='center', loc='upper left', bbox=[0.01,0.72,0.38,0.22])
        tab.auto_set_font_size(False); tab.set_fontsize(9); tab.scale(1.05,1.05)

    pts = get_half_hour_points(df_res, date_str)
    # intervals: [t0->t1] = 14:00-14:30, [t1->t2] = 14:30-15:00
    intervals = []
    if pts.get('t0') is not None and pts.get('t1') is not None:
        intervals.append(('stmt_half', pts['t0'], pts['c0'], pts['t1'], pts['c1']))
    if pts.get('t1') is not None and pts.get('t2') is not None:
        intervals.append(('press_half', pts['t1'], pts['c1'], pts['t2'], pts['c2']))

    # decide color per interval
    for name, ta, ca, tb, cb in intervals:
        change = cb - ca
        color = 'grey'  # default ambiguous
        label = ''
        # choose ratio: stmt_half uses statement hawk; press_half uses press hawk
        if name == 'stmt_half':
            ratio = (mone_rat['hawkish_pct']/100.0) if mone_rat else None
            label = 'Statement half'
        else:
            ratio = (pres_rat['hawkish_pct']/100.0) if pres_rat else None
            label = 'Press half'
        if ratio is None:
            color='grey'
            reason = "missing_ratio"
        else:
            # expected: if ratio > H_THRESH -> expect downward, if ratio < 1-H_THRESH -> expect upward, else ambiguous
            if ratio > H_THRESH:
                expected = -1
            elif ratio < (1.0 - H_THRESH):
                expected = 1
            else:
                expected = 0
            actual = 0
            if change > 0:
                actual = 1
            elif change < 0:
                actual = -1
            else:
                actual = 0
            if expected == 0:
                color = 'grey'
                reason = "expected_ambiguous"
            else:
                if actual == expected:
                    color = 'green'; reason = "match"
                else:
                    color = 'red'; reason = "mismatch"
        # plot thick segment
        ax.plot([ta, tb], [ca, cb], linewidth=4, color=color, solid_capstyle='round', zorder=5)
        mid_t = ta + (tb - ta)/2
        mid_y = (ca + cb)/2
        ax.text(mid_t, mid_y, f"{name.split('_')[0].upper()} {color.upper()}", fontsize=9, fontweight='bold', ha='center', va='bottom', color=color)
        print(f"  Interval {name}: {ta.strftime('%H:%M')}->{tb.strftime('%H:%M')} change={cb-ca:.4f} ratio={ratio if ratio is not None else 'N/A'} => {color} ({reason})")

    plt.tight_layout()
    fig.savefig(out_png_path)
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description="Plot local 1-min CSVs (two half-hour comparisons)")
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (ET)")
    parser.add_argument("--data-dir-template", default="/data/polygon_1m_full_{ticker}")
    parser.add_argument("--agg-interval", default="2min")
    parser.add_argument("--outdir", default="results_local")
    parser.add_argument("--stmt-time", default=None)
    parser.add_argument("--pc-time", default=None)
    parser.add_argument("--mone-template", default=None)
    parser.add_argument("--pres-template", default=None)
    parser.add_argument("--H-thresh", type=float, default=0.50, help="hawk ratio threshold to declare 'hawkish' (default 0.50)")
    args = parser.parse_args()

    ensure_dir(args.outdir)
    plots_out = os.path.join(args.outdir, "plots"); ensure_dir(plots_out)
    csv_out = os.path.join(args.outdir, "csv"); ensure_dir(csv_out)

    stmt_dt = None; pc_dt = None
    if args.stmt_time:
        stmt_dt = NY.localize(datetime.strptime(args.stmt_time, "%Y-%m-%d %H:%M"))
    if args.pc_time:
        pc_dt = NY.localize(datetime.strptime(args.pc_time, "%Y-%m-%d %H:%M"))

    for tk in args.tickers:
        print(f"\n=== {tk} ===")
        data_dir = args.data_dir_template.format(ticker=tk)
        csvs = find_csvs_for_date(data_dir, args.date)
        if not csvs:
            print(f" No CSVs found in {data_dir} for date {args.date}.")
            continue
        print(f" Found {len(csvs)} csv(s); using: {csvs}")
        df = read_and_concat_csvs(csvs)
        if df is None or df.empty:
            print("  -> combined dataframe empty.")
            continue
        try:
            df_res = resample_ohlcv(df, args.agg_interval)
        except Exception as e:
            print(f"  -> resample failed: {e}")
            continue
        df_res = df_res.between_time("09:30","16:00")
        if df_res.empty:
            print("  -> no data in market hours after resample.")
            continue

        out_csv_path = os.path.join(csv_out, f"{tk}_{args.agg_interval}_{args.date}_ET.csv")
        out_png_path = os.path.join(plots_out, f"{tk}_{args.agg_interval}_{args.date}_with_sentiment.png")
        mone_path = args.mone_template.format(date=args.date) if args.mone_template else None
        pres_path = args.pres_template.format(date=args.date) if args.pres_template else None

        print(f" Saving CSV -> {out_csv_path}")
        print(f" Saving PNG -> {out_png_path}")
        plot_and_save(df_res, tk, args.date, args.agg_interval, out_csv_path, out_png_path, stmt_dt=stmt_dt, pc_dt=pc_dt, mone_csv=mone_path, pres_csv=pres_path, H_THRESH=args.H_thresh)

    print("\nDone.")

if __name__ == "__main__":
    main()
