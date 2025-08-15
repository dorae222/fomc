import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
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
    return df

# ------------------------------
# 분석
# ------------------------------
def analyze(fomc_df, sp500_df, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    results = []
    for idx, row in fomc_df.iterrows():
        date = row['date']
        if date in sp500_df.index.date:
            close_price = sp500_df.loc[sp500_df.index.date == date, 'Close'].values[0]
            results.append({"date": date, "close": close_price, "type": row['type']})
    results_df = pd.DataFrame(results)
    results_df.to_csv(os.path.join(output_dir, "fomc_sp500.csv"), index=False)
    
    # 간단 차트
    plt.figure(figsize=(12,6))
    plt.plot(results_df['date'], results_df['close'], marker='o')
    plt.title("S&P500 on FOMC Dates")
    plt.xlabel("Date")
    plt.ylabel("Close")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "fomc_sp500_plot.png"))
    print(f"[완료] 결과 CSV와 차트 저장: {output_dir}")

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

    # S&P500
    sp500_df = load_sp500_data(start_dt, end_dt, source=args.sp_source, csv_path=args.sp_csv)
    print(f"[완료] S&P500 데이터 로드 ({len(sp500_df)}개 행)")

    # FOMC
    if args.auto_scrape_fomc:
        print("[알림] 자동 스크래핑 기능은 현재 CSV 사용 권장")
        fomc_df = pd.DataFrame()  # 기존 스크래핑 기능 비활성화
    else:
        if not args.fomc_csv:
            raise ValueError("FOMC CSV를 제공해야 합니다 (--fomc-csv)")
        fomc_df = load_fomc_csv(args.fomc_csv)
    print(f"[완료] FOMC 날짜 CSV 로드: {args.fomc_csv}")

    # 분석
    analyze(fomc_df, sp500_df, args.output_dir)
