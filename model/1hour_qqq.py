# pip install yfinance pytz pandas matplotlib
import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경에서 안전

import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
from pathlib import Path

# --- Robust path resolution (script-location based) ---
from pathlib import Path
SCRIPT_PATH = Path(__file__).resolve()
# Candidate roots to locate project root (usually SCRIPT_PATH.parents[1] -> fomc_clean)
POTENTIAL_ROOTS = [
    SCRIPT_PATH.parents[1] if len(SCRIPT_PATH.parents) > 1 else SCRIPT_PATH.parent,
    SCRIPT_PATH.parents[2] if len(SCRIPT_PATH.parents) > 2 else SCRIPT_PATH.parent,
    Path.cwd(),
    Path("/home/cora3/workSpace/fomc_clean")
]

PRED_DIR = None
for root in POTENTIAL_ROOTS:
    cand = root / "predicted" / "txt_pred"
    if cand.exists():
        PRED_DIR = cand
        break

# fallback: walk up from script path up to 6 levels and try
if PRED_DIR is None:
    p = SCRIPT_PATH
    for _ in range(6):
        cand = p / "predicted" / "txt_pred"
        if cand.exists():
            PRED_DIR = cand
            break
        p = p.parent

if PRED_DIR is None:
    raise SystemExit(f"No predicted/txt_pred directory found. Checked: {POTENTIAL_ROOTS}")

# Define output directories relative to PRED_DIR
RESULTS_DIR = PRED_DIR
CSV_SAVE_DIR = RESULTS_DIR / "csv"
PLOTS_SAVE_DIR = RESULTS_DIR / "plots"
CSV_SAVE_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_SAVE_DIR.mkdir(parents=True, exist_ok=True)

print("Using PRED_DIR =", PRED_DIR)
# --- define DATA_DIR and common output dirs expected by the script ---
from pathlib import Path as _Path  # local alias to avoid shadowing if Path already imported

SCRIPT_DIR = _Path(__file__).resolve().parent    # .../fomc_clean/model
BASE_DIR = SCRIPT_DIR.parent                     # .../fomc_clean
DATA_DIR = BASE_DIR / "data"                     # where fomc_dates_template.csv should live

# ensure CSV/plots dirs under predicted/txt_pred exist (script expects these)
# PRED_DIR should be a Path object; if it's a string, convert: PRED_DIR = _Path(PRED_DIR)
if not isinstance(PRED_DIR, _Path):
    PRED_DIR = _Path(PRED_DIR)

CSV_SAVE_DIR = PRED_DIR / "csv"
PLOTS_SAVE_DIR = PRED_DIR / "plots"
CSV_SAVE_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_SAVE_DIR.mkdir(parents=True, exist_ok=True)

# debug prints (optional)
print("Using DATA_DIR =", DATA_DIR)
print("CSV_SAVE_DIR =", CSV_SAVE_DIR)
print("PLOTS_SAVE_DIR =", PLOTS_SAVE_DIR)

# 결과 디렉토리 생성
CSV_SAVE_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_SAVE_DIR.mkdir(parents=True, exist_ok=True)

# timezone
tz_ny = pytz.timezone("America/New_York")

# Load FOMC dates (파일이 없으면 명확한 에러 메세지 출력)
fomc_dates_file = DATA_DIR / "fomc_dates_template.csv"
if not fomc_dates_file.exists():
    raise FileNotFoundError(f"FOMC dates file not found: {fomc_dates_file}")
fomc_dates_df = pd.read_csv(fomc_dates_file)

# Filter for the last 2 years
fomc_dates_df['date'] = pd.to_datetime(fomc_dates_df['date'])
fomc_dates_df = fomc_dates_df[fomc_dates_df['date'] >= (datetime.now() - pd.DateOffset(years=2))]
fomc_dates_df['date'] = fomc_dates_df['date'].dt.strftime('%Y-%m-%d')


# Calculate sentiment ratios
def calculate_ratios(df_sentiment):
    total_count = len(df_sentiment)
    dovish_count = df_sentiment[df_sentiment['pred_label'] == 'dovish'].shape[0]
    hawkish_count = df_sentiment[df_sentiment['pred_label'] == 'hawkish'].shape[0]
    neutral_count = df_sentiment[df_sentiment['pred_label'] == 'neutral'].shape[0]

    dovish_ratio = (dovish_count / total_count) * 100 if total_count > 0 else 0
    hawkish_ratio = (hawkish_count / total_count) * 100 if total_count > 0 else 0
    neutral_ratio = (neutral_count / total_count) * 100 if total_count > 0 else 0

    return dovish_ratio, hawkish_ratio, neutral_ratio


# Helper: find likely label column and normalize to "pred_label"
LABEL_CANDIDATES = ["pred_label", "predlabel", "pred", "label", "prediction", "predicted"]

def normalize_label_column(df):
    # returns new df (copy) that contains 'pred_label' normalized to 'dovish'/'hawkish'/'neutral'
    if df is None or df.empty:
        return pd.DataFrame()
    df2 = df.copy()
    found = None
    for col in df2.columns:
        low = col.lower()
        for cand in LABEL_CANDIDATES:
            if low == cand or cand in low:
                found = col
                break
        if found:
            break

    if not found:
        # no label-like column found
        return pd.DataFrame()

    def normalize_val(v):
        try:
            s = str(v).strip().lower()
        except Exception:
            return 'neutral'
        if 'hawk' in s:
            return 'hawkish'
        if 'dov' in s or 'dove' in s:
            return 'dovish'
        if 'neu' in s:
            return 'neutral'
        # if it's numeric probabilities etc, fallback to neutral
        return 'neutral'

    df2['pred_label'] = df2[found].apply(normalize_val)
    return df2


for index, row in fomc_dates_df.iterrows():
    date_str = row['date']                 # 'YYYY-MM-DD'
    year, month, day = map(int, date_str.split('-'))
    date_nodash = date_str.replace('-', '')

    # FOMC 당일 (ET)
    start_et = tz_ny.localize(datetime(year, month, day, 9, 25))   # 장시작 직전부터
    end_et   = tz_ny.localize(datetime(year, month, day, 16, 5))   # 장마감 직후까지

    # yfinance 다운로드 (에러 발생시 건너뜀)
    try:
        df = yf.download(
            "QQQ",
            interval="1h",
            start=start_et.astimezone(pytz.UTC),
            end=end_et.astimezone(pytz.UTC),
            auto_adjust=False,
            progress=False
        )
    except Exception as e:
        print(f"YFinance download failed for {date_str}: {e}")
        print(f"No QQQ data found for {date_str}. Skipping.")
        continue

    # 인덱스 타임존 처리 (빈 DataFrame 체크 포함)
    if df.empty:
        print(f"No QQQ data found for {date_str}. Skipping.")
        continue

    if df.index.tz is not None:
        df = df.tz_convert(tz_ny)
    else:
        df.index = df.index.tz_localize(pytz.UTC).tz_convert(tz_ny)

    # 장중(09:30~16:00)만 필터
    df = df.between_time("09:30", "16:00")
    if df.empty:
        print(f"No QQQ data in market hours for {date_str}. Skipping.")
        continue

    # --- CSV 저장 (results/csv/) ---
    qqq_csv_filename = CSV_SAVE_DIR / f"QQQ_1h_{date_str}_ET.csv"
    df.to_csv(qqq_csv_filename)
    print(f"saved -> {qqq_csv_filename}")

    # 차트 그리기 (항상 성명/기자회견 시점은 표시)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df.index, df["Close"], linewidth=1, label="QQQ Close")

    # FOMC 타임스탬프 (ET) — 항상 찍음
    stmt_time = tz_ny.localize(datetime(year, month, day, 14, 0))   # 성명문
    pc_time   = tz_ny.localize(datetime(year, month, day, 14, 30))  # 기자회견

    for t, label in [(stmt_time, "Statement 14:00 ET"),
                     (pc_time,   "Press Conf 14:30 ET")]:
        ax.axvline(t, linestyle="--", linewidth=1)
        # 텍스트가 인덱스 범위 밖으로 벗어나지 않게 안전하게 y 위치 계산
        y_top = ax.get_ylim()[1]
        ax.text(t, y_top, label, va="bottom", ha="left", rotation=90, fontsize=8)

    # sentiment 파일 경로 (스크립트 기준의 results 폴더)
    pres_csv_path = RESULTS_DIR / f"pred_{date_nodash}pres.csv"
    mone_csv_path = RESULTS_DIR / f"pred_{date_nodash}mone.csv"

    df_pres = pd.DataFrame()
    df_mone = pd.DataFrame()

    if pres_csv_path.exists():
        try:
            df_pres = pd.read_csv(pres_csv_path)
        except Exception as e:
            print(f"Failed to read {pres_csv_path}: {e}")
    else:
        print(f"Warning: Press conference sentiment data not found for {date_str} at {pres_csv_path}")

    if mone_csv_path.exists():
        try:
            df_mone = pd.read_csv(mone_csv_path)
        except Exception as e:
            print(f"Failed to read {mone_csv_path}: {e}")
    else:
        print(f"Warning: Statement sentiment data not found for {date_str} at {mone_csv_path}")

    # Normalize label columns (robust)
    norm_pres = normalize_label_column(df_pres) if not df_pres.empty else pd.DataFrame()
    norm_mone = normalize_label_column(df_mone) if not df_mone.empty else pd.DataFrame()

    # sentiment 파일이 하나라도 있으면 표(table) 추가 (ratio 계산)
    if not norm_pres.empty or not norm_mone.empty:
        if not norm_mone.empty:
            mone_dovish, mone_hawkish, mone_neutral = calculate_ratios(norm_mone)
        else:
            mone_dovish, mone_hawkish, mone_neutral = (0, 0, 0)

        if not norm_pres.empty:
            pres_dovish, pres_hawkish, pres_neutral = calculate_ratios(norm_pres)
        else:
            pres_dovish, pres_hawkish, pres_neutral = (0, 0, 0)

        table_data = [
            ["Category", "Dovish (%)", "Hawkish (%)", "Neutral (%)"],
            ["Statement", f"{mone_dovish:.2f}", f"{mone_hawkish:.2f}", f"{mone_neutral:.2f}"],
            ["Press Conf.", f"{pres_dovish:.2f}", f"{pres_hawkish:.2f}", f"{pres_neutral:.2f}"]
        ]

        table = ax.table(cellText=table_data,
                         colLabels=None,
                         cellLoc='center',
                         loc='upper left',
                         bbox=[0.01, 0.70, 0.38, 0.22])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.0, 1.0)
    else:
        # sentiment 정보 없으면 표 없이 (요청하신 대로) 가격 차트 + 시점만 표시
        print(f"Skipping sentiment table for {date_str} (no sentiment files or label column).")

    # 포맷팅 & 저장
    ax.set_title(f"QQQ 1-hour bars on {date_str} (ET)")
    ax.set_xlabel("Time (America/New_York)")
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz_ny))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    output_png_filename = PLOTS_SAVE_DIR / f"QQQ_1h_{date_str}_with_sentiment.png"
    plt.savefig(output_png_filename)
    print(f"saved -> {output_png_filename}")
    plt.close(fig)
