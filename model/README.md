# FOMC Impact Analysis Model

This script analyzes the impact of FOMC announcements on a given stock index.

## How to Run

There are two ways to run the script:

### 1. From the project root directory (`fomc/`)

This is the recommended way.

```bash
python model/fomc_impact_analysis.py \
    --ticker ^GSPC \
    --sp-source yfinance \
    --fomc-csv data/fomc_dates_template.csv \
    --start 1994-01-01 \
    --end 2025-12-31 \
    --output-dir output
```

### 2. From the `model/` directory

If you are inside the `model` directory, you need to adjust the paths for the data and output directories.

```bash
python fomc_impact_analysis.py \
    --ticker ^GSPC \
    --sp-source yfinance \
    --fomc-csv ../data/fomc_dates_template.csv \
    --start 1994-01-01 \
    --end 2025-12-31 \
    --output-dir ../output
```

## Command-Line Arguments

*   `--ticker`: Ticker for the index (e.g., `^GSPC` for S&P 500, `^IXIC` for NASDAQ). Default is `^IXIC`.
*   `--sp-source`: Source for the index data. Can be `yfinance` or `csv`. Default is `yfinance`.
*   `--sp-csv`: Path to the index data CSV file (if `sp-source` is `csv`).
*   `--fomc-csv`: **Required.** Path to the FOMC dates CSV file.
*   `--start`: **Required.** Start date for the analysis (YYYY-MM-DD).
*   `--end`: **Required.** End date for the analysis (YYYY-MM-DD).
*   `--output-dir`: **Required.** Directory to save the output files (CSV and plot).

```
