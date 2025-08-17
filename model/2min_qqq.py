# pip install yfinance pytz pandas matplotlib
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime

tz_ny = pytz.timezone("America/New_York")

# FOMC 당일: 2025-07-30 (ET)

start_et = tz_ny.localize(datetime(2025, 7, 30, 9, 25))   # 장시작 직전부터
end_et   = tz_ny.localize(datetime(2025, 7, 30, 16, 5))   # 장마감 직후까지

# yfinance는 tz-aware datetime을 UTC로 변환해 요청해도 처리됨
df = yf.download(
    "QQQ",
    interval="2m",
    start=start_et.astimezone(pytz.UTC),
    end=end_et.astimezone(pytz.UTC),
    auto_adjust=False,   # 필요시 True로 (배당/분할 보정)
    progress=False
)

# 인덱스가 tz-aware이면 NY시간대로 변환
if df.index.tz is not None:
    df = df.tz_convert(tz_ny)
else:
    df.index = df.index.tz_localize(pytz.UTC).tz_convert(tz_ny)

# 장중(09:30~16:00)만 필터
df = df.between_time("09:30", "16:00")

# 결과 확인 & 저장
print(df.head())
df.to_csv("QQQ_2m_2025-07-30_ET.csv")
print("saved -> QQQ_2m_2025-07-30_ET.csv")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(df.index, df["Close"], linewidth=1)

# FOMC 타임스탬프 (ET)
stmt_time = tz_ny.localize(datetime(2025, 7, 30, 14, 0))   # 성명문
pc_time   = tz_ny.localize(datetime(2025, 7, 30, 14, 30))  # 기자회견 시작

# 수직선 + 라벨
for t, label in [(stmt_time, "Statement 14:00 ET"),
                 (pc_time,   "Press Conf 14:30 ET")]:
    ax.axvline(t, linestyle="--", linewidth=1)
    ax.text(t, ax.get_ylim()[1], label, va="bottom", ha="left", rotation=90)

# 포맷팅
ax.set_title("QQQ 2-minute bars on 2025-07-30 (ET)")
ax.set_xlabel("Time (America/New_York)")
ax.set_ylabel("Price")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz_ny))
ax.grid(True, alpha=0.3)
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

# Load sentiment prediction data
df_pres = pd.read_csv("/home/cora3/workSpace/fomc_py/fomc/results/pred_20250730pres.csv")
df_mone = pd.read_csv("/home/cora3/workSpace/fomc_py/fomc/results/pred_20250730mone.csv")

# Calculate ratios for statement and press conference
mone_dovish, mone_hawkish, mone_neutral = calculate_ratios(df_mone)
pres_dovish, pres_hawkish, pres_neutral = calculate_ratios(df_pres)

# Prepare table data
table_data = [
    ["Category", "Dovish (%)", "Hawkish (%)", "Neutral (%)"],
    ["Statement", f"{mone_dovish:.2f}", f"{mone_hawkish:.2f}", f"{mone_neutral:.2f}"],
    ["Press Conf.", f"{pres_dovish:.2f}", f"{pres_hawkish:.2f}", f"{pres_neutral:.2f}"]
]

# Add table to the plot
table = ax.table(cellText=table_data,
                     colLabels=None,
                     cellLoc='center',
                     loc='upper left',
                     bbox=[0.0, 0.75, 0.4, 0.2]) # Adjust bbox to position the table

table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.2, 1.2) # Adjust table size

plt.tight_layout()
plt.savefig("QQQ_2m_2025-07-30_with_sentiment.png")
print("saved -> QQQ_2m_2025-07-30_with_sentiment.png")
