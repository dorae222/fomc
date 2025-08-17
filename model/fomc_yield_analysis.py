

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import argparse
import os
from datetime import timedelta

def load_data(fomc_path, yield_path):
    """Loads FOMC dates and Treasury yield data from CSV files."""
    print(f"Loading FOMC data from: {fomc_path}")
    fomc_df = pd.read_csv(fomc_path, parse_dates=['date'])
    
    print(f"Loading 2-Year Treasury yield data from: {yield_path}")
    yield_df = pd.read_csv(yield_path, parse_dates=['DATE'])
    yield_df.rename(columns={'DATE': 'date', 'DGS2': 'yield'}, inplace=True)
    
    # FRED data uses '.' for non-trading days. Filter them out and convert to numeric.
    yield_df = yield_df[yield_df['yield'] != '.'].copy()
    yield_df['yield'] = pd.to_numeric(yield_df['yield'])
    
    # Forward-fill NaNs for up to 3 days to handle holidays
    yield_df.set_index('date', inplace=True)
    yield_df = yield_df.resample('D').ffill(limit=3)
    yield_df.reset_index(inplace=True)

    return fomc_df, yield_df

def analyze_yield_reaction(fomc_df, yield_df, output_dir):
    """Analyzes and visualizes the 2-year yield reaction to FOMC decisions."""
    print("Analyzing yield reaction...")
    results = []
    yield_df.set_index('date', inplace=True)

    for _, row in fomc_df.iterrows():
        fomc_date = row['date']
        
        try:
            # Find yield on FOMC day (T) and day after (T+1)
            yield_t0 = yield_df.loc[fomc_date, 'yield']
            yield_t1 = yield_df.loc[fomc_date + timedelta(days=1), 'yield']
            
            # Calculate the change in basis points (1% = 100 bps)
            yield_change_bps = (yield_t1 - yield_t0) * 100
            
            results.append({
                'date': fomc_date,
                'rate_change': row['rate_change'],
                'yield_t0': yield_t0,
                'yield_t1': yield_t1,
                'yield_change_bps': yield_change_bps
            })
        except KeyError:
            # Skip if the date or the next day is not in the yield data (e.g., weekend/holiday)
            print(f"Skipping {fomc_date.strftime('%Y-%m-%d')}: Data not available.")
            continue

    results_df = pd.DataFrame(results)
    results_df.dropna(inplace=True)


    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # --- Plot 1: Simple Two-Color Plot (Yield Change) ---
    print("Creating simple two-color plot...")
    fig1, ax1 = plt.subplots(figsize=(18, 7))
    
    simple_colors = ['red' if x >= 0 else 'blue' for x in results_df['yield_change_bps']]

    bars = ax1.bar(results_df['date'], results_df['yield_change_bps'], color=simple_colors, width=25, alpha=0.7)
    
    # Add text labels for FOMC rate change on each bar
    for bar, rate_change in zip(bars, results_df['rate_change']):
        y_value = bar.get_height()
        label = f"{rate_change:+.2f}"
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            y_value,
            label,
            ha='center',
            va='bottom' if y_value >= 0 else 'top',
            fontsize=7,
            color='black'
        )

    ax1.set_title('1-Day Change in 2-Year Treasury Yield after FOMC Decision (Up/Down)', fontsize=16)
    ax1.set_xlabel('Date', fontsize=12)
    ax1.set_ylabel('Yield Change (Basis Points)', fontsize=12)
    ax1.axhline(0, color='grey', linestyle='--')
    ax1.grid(True, axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()

    plot_path_simple = os.path.join(output_dir, "fomc_2y_yield_reaction.png")
    plt.savefig(plot_path_simple)
    print(f"Simple plot saved to {plot_path_simple}")
    plt.close(fig1)

    # --- Plot 2: Colormap Plot (FOMC Rate Change) ---
    print("Creating colormap plot...")
    fig2, ax2 = plt.subplots(figsize=(18, 7))
    
    rate_changes = results_df['rate_change']
    norm = mcolors.TwoSlopeNorm(vmin=rate_changes.min(), vcenter=0, vmax=rate_changes.max())
    cmap = plt.get_cmap('RdBu_r')
    bar_colors = cmap(norm(rate_changes.values))
    
    ax2.bar(results_df['date'], results_df['yield_change_bps'], color=bar_colors, width=25, alpha=0.7)
    
    ax2.set_title('1-Day Change in 2-Year Treasury Yield (Colored by FOMC Action)', fontsize=16)
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Yield Change (Basis Points)', fontsize=12)
    
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig2.colorbar(sm, ax=ax2)
    cbar.set_label('FOMC Rate Change (%)', fontsize=12)
    
    ax2.axhline(0, color='grey', linestyle='--')
    ax2.grid(True, axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()

    plot_path_colored = os.path.join(output_dir, "fomc_2y_yield_reaction_colored.png")
    plt.savefig(plot_path_colored)
    print(f"Colormap plot saved to {plot_path_colored}")
    plt.close(fig2)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze 2-Year Treasury Yield reaction to FOMC announcements.')
    parser.add_argument('--fomc-csv', type=str, default='data/fomc_dates_template.csv', help='Path to the FOMC dates CSV file.')
    parser.add_argument('--yield-csv', type=str, default='output/DGS2.csv', help='Path to the 2-Year Treasury yield (DGS2) CSV file.')
    parser.add_argument('--output-dir', type=str, default='output', help='Directory to save the output plot.')
    args = parser.parse_args()

    fomc_df, yield_df = load_data(args.fomc_csv, args.yield_csv)
    analyze_yield_reaction(fomc_df, yield_df, args.output_dir)
