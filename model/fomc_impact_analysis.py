import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경에서도 PNG 저장 가능
import matplotlib.pyplot as plt
import argparse

# ------------------------------
# Generic Index Data Loader
# ------------------------------
def load_index_data(ticker, start_dt, end_dt):
    print(f"Downloading data for {ticker}...")
    df = yf.download(ticker, start=start_dt.strftime("%Y-%m-%d"),
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
        df['rate_change'] = 0.0
    df['rate_change'] = df['rate_change'].astype(float)
    return df

# ------------------------------
# 분석 및 시각화
# ------------------------------
def analyze(fomc_df, index_df, output_dir, ticker):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    results = []
    for idx, row in fomc_df.iterrows():
        date = row['date']
        if date in index_df.index.date:
            open_price = index_df.loc[index_df.index.date == date, 'Open'].values[0]
            close_price = index_df.loc[index_df.index.date == date, 'Close'].values[0]
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
    results_df = results_df.dropna(subset=['diff'])
    results_df['diff'] = results_df['diff'].astype(float)
    results_df['date_str'] = results_df['date'].astype(str)

    # Sanitize ticker for filename
    safe_ticker = ticker.replace('^', '')
    
    # CSV 저장
    csv_path = os.path.join(output_dir, f"fomc_{safe_ticker}.csv")
    results_df.to_csv(csv_path, index=False)

    colors = ['skyblue' if x >= 0 else 'salmon' for x in results_df['diff']]

    plt.figure(figsize=(14,6))
    bars = plt.bar(results_df['date_str'], results_df['diff'], color=colors)
    plt.axhline(0, color='red', linestyle='--')
    plt.title(f"{ticker} Open-Close Difference on FOMC Dates") # Use ticker in title
    plt.xlabel("Date")
    plt.ylabel("Close - Open")

    for bar, rate in zip(bars, results_df['rate_change']):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                 f"{rate:+.2f}", ha='center',
                 va='bottom' if bar.get_height()>=0 else 'top',
                 fontsize=8)

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
    
    plot_path = os.path.join(output_dir, f"fomc_{safe_ticker}_plot_diff.png")
    plt.savefig(plot_path)
    plt.close()

    print(f"[완료] CSV: {csv_path}\n[완료] Plot: {plot_path}")

# ------------------------------
# 메인
# ------------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    # ticker는 나스닥 100 지수로 기본값 설정 ^IXIC , # S&P500은 ^GSPC로 설정, 나스닥 100은 ^NDX   
    parser.add_argument('--ticker', default='^IXIC', help='Ticker for index (default S&P500 ^GSPC)')
    parser.add_argument('--sp-source', choices=['yfinance','csv'], default='yfinance',
                        help='Source for S&P500 data')
    parser.add_argument('--sp-csv', help='Path to S&P500 CSV file (if source=csv)')
    parser.add_argument('--fomc-csv', required=True, help='Path to FOMC CSV file')
    parser.add_argument('--start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    index_df = load_index_data(args.ticker, start_dt, end_dt)
    print(f"[완료] {args.ticker} 데이터 로드 ({len(index_df)}개 행)")

    fomc_df = load_fomc_csv(args.fomc_csv)
    print(f"[완료] FOMC 날짜 CSV 로드: {args.fomc_csv}")

    analyze(fomc_df, index_df, args.output_dir, args.ticker)