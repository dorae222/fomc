import pandas as pd
import re

def analyze_correlation():
    """
    Analyzes the correlation between FOMC interest rate change, dovish ratio,
    and NASDAQ percentage change.
    """
    # Load the summary data
    summary_df = pd.read_csv('output/split_predictions/summary.csv')

    # Filter for transcripts
    summary_df = summary_df[summary_df['Unnamed: 0'].str.contains('transcript', na=False)]

    # Extract date from filename
    summary_df['date_str'] = summary_df['Unnamed: 0'].apply(lambda x: re.search(r'(\d{8})', x).group(1) if re.search(r'(\d{8})', x) else None)
    summary_df = summary_df.dropna(subset=['date_str'])
    summary_df['date'] = pd.to_datetime(summary_df['date_str'], format='%Y%m%d')

    # Load the IXIC pct data
    ixic_df = pd.read_csv('output/fomc_IXIC_pct.csv')
    ixic_df['date'] = pd.to_datetime(ixic_df['date'])

    # Merge the two dataframes
    merged_df = pd.merge(summary_df, ixic_df, on='date')

    # Select columns for correlation analysis
    correlation_df = merged_df[['rate_change', 'dovish_ratio', 'diff_pct']]

    # Calculate the correlation matrix
    correlation_matrix = correlation_df.corr()

    print("Correlation Matrix:")
    print(correlation_matrix)

if __name__ == '__main__':
    analyze_correlation()
