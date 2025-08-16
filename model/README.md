# FOMC Impact Analysis Model


This file describes the analysis scripts located in the `model/` directory.

---

## Stock Market Impact Analysis (`fomc_impact_analysis.py`)

This script analyzes the impact of FOMC announcements on a given stock index.

### How to Run

There are two ways to run the script:

#### 1. From the project root directory (`fomc/`)

This is the recommended way.

```bash
python model/fomc_impact_analysis.py \
    --ticker ^GSPC \
    --fomc-csv data/fomc_dates_template.csv \
    --start 1994-01-01 \
    --end 2025-12-31 \
    --output-dir output
```

#### 2. From the `model/` directory

If you are inside the `model` directory, you need to adjust the paths for the data and output directories.

```bash
python fomc_impact_analysis.py \
    --ticker ^GSPC \
    --fomc-csv ../data/fomc_dates_template.csv \
    --start 1994-01-01 \
    --end 2025-12-31 \
    --output-dir ../output
```

### Command-Line Arguments

*   `--ticker`: Ticker for the index (e.g., `^GSPC` for S&P 500, `^IXIC` for NASDAQ). Default is `^IXIC`.
*   `--fomc-csv`: **Required.** Path to the FOMC dates CSV file.
*   `--start`: **Required.** Start date for the analysis (YYYY-MM-DD).
*   `--end`: **Required.** End date for the analysis (YYYY-MM-DD).
*   `--output-dir`: **Required.** Directory to save the output files (CSV and plot).

---

## 2-Year Treasury Yield Reaction Analysis (`fomc_yield_analysis.py`)

This script analyzes the reaction of the 2-year US Treasury yield to FOMC interest rate decisions. It measures the 1-day change in the yield following an announcement and generates two visualizations:

1.  A simple plot showing the yield change direction (up/down) with the FOMC's rate decision annotated on each bar.
2.  A colormap plot where the bar color represents the magnitude and direction of the FOMC's rate decision.

### How to Run

The script can be run from the project root directory. It uses default paths for the required CSV files.

```bash
python model/fomc_yield_analysis.py
```

### Command-Line Arguments

*   `--fomc-csv`: Path to the FOMC dates CSV file. (Default: `data/fomc_dates_template.csv`)
*   `--yield-csv`: Path to the 2-Year Treasury yield (DGS2) CSV file. (Default: `output/DGS2.csv`)
*   `--output-dir`: Directory to save the output plots. (Default: `output`)

```