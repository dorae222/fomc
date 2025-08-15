import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경에서도 PNG 저장 가능
import matplotlib.pyplot as plt
import argparse

# ------------------------------
# S&P500 데이터 로드
# ------------------------------
def load_sp500_data(start_dt, end_dt, source="yfinance", csv_path=None):
    if source == "csv":
        df = pd.read_csv(csv_path, parse_dates=["Date"])
        df.set_index("Date", inplace=True)
    else:
        df = yf.download("^GSPC", start=start_dt.strftime("%Y-%m-%d"),
                         end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                         progress=False, auto_adjust=True)
    return df

# ------------------------------
# FOMC CSV 로드
# ------------------------------
def load_fomc_csv(csv_path):
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df['type'] = df['type'].astype(str)
    if 'rate_change' not in df.columns:
        df['rate_change'] = 0.0  # 금리 변동 폭이 없으면 0으로 초기화
    df['rate_change'] = df['rate_change'].astype(float)
    return df

# ------------------------------
# 분석 및 시각화
# ------------------------------
def analyze(fomc_df, sp500_df, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    results = []
    for idx, row in fomc_df.iterrows():
        date = row['date']
        if date in sp500_df.index.date:
            open_price = sp500_df.loc[sp500_df.index.date == date, 'Open'].values[0]
            close_price = sp500_df.loc[sp500_df.index.date == date, 'Close'].values[0]
            diff = close_price - open_price
            results.append({
                "date": date,
                "open": open_price,
                "close": close_price,
                "diff": diff,
                "type": row['type'],
                "rate_change": row['rate_change']
            })

    results_df = pd.DataFrame(results)

    # NaN 제거 및 타입 변환
    results_df = results_df.dropna(subset=['diff'])
    results_df['diff'] = results_df['diff'].astype(float)
    results_df['date_str'] = results_df['date'].astype(str)

    # CSV 저장
    results_df.to_csv(os.path.join(output_dir, "fomc_sp500.csv"), index=False)

    # 색상: diff 양수 = 파랑, 음수 = 주황
    colors = ['skyblue' if x >= 0 else 'salmon' for x in results_df['diff']]

    # 막대그래프
    plt.figure(figsize=(14,6))
    bars = plt.bar(results_df['date_str'], results_df['diff'], color=colors)
    plt.axhline(0, color='red', linestyle='--')
    plt.title("S&P500 Open-Close Difference on FOMC Dates")
    plt.xlabel("Date")
    plt.ylabel("Close - Open")

    # 금리 변동 폭 표시
    for bar, rate in zip(bars, results_df['rate_change']):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                 f"{rate:+.2f}", ha='center',
                 va='bottom' if bar.get_height()>=0 else 'top',
                 fontsize=8)

    # X축 레이블 가독성 개선 (연도별 표시)
    tick_locations = []
    tick_labels = []
    current_year = None
    for i, date_str in enumerate(results_df['date_str']):
        year = date_str.split('-')[0]
        if year != current_year:
            tick_locations.append(i)
            tick_labels.append(year)
            current_year = year
    
    plt.xticks(ticks=tick_locations, labels=tick_labels, rotation=0, ha="center")
    plt.grid(True, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "fomc_sp500_plot_diff.png"))
    plt.close()

    print(f"[완료] CSV와 시각화 저장: {output_dir}")

# ------------------------------
# 메인
# ------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--sp-source', choices=['yfinance','csv'], default='yfinance')
    parser.add_argument('--sp-csv', help='S&P500 CSV 경로')
    parser.add_argument('--fomc-csv', help='FOMC CSV 경로')
    parser.add_argument('--auto-scrape-fomc', action='store_true', help='자동 스크래핑 시도')
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    # S&P500 데이터 로드
    sp500_df = load_sp500_data(start_dt, end_dt, source=args.sp_source, csv_path=args.sp_csv)
    print(f"[완료] S&P500 데이터 로드 ({len(sp500_df)}개 행)")

    # FOMC 데이터 로드
    if args.auto_scrape_fomc:
        print("[알림] 자동 스크래핑 기능은 현재 CSV 사용 권장")
        fomc_df = pd.DataFrame()
    else:
        if not args.fomc_csv:
            raise ValueError("FOMC CSV를 제공해야 합니다 (--fomc-csv)")
        fomc_df = load_fomc_csv(args.fomc_csv)
    print(f"[완료] FOMC 날짜 CSV 로드: {args.fomc_csv}")

    # 분석 및 시각화
    analyze(fomc_df, sp500_df, args.output_dir)
