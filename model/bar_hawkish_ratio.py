import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import re

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

# Create the bar plot
fig, ax = plt.subplots(figsize=(15, 7))

# Create a colormap
norm = mcolors.Normalize(vmin=merged_df['hawkish_ratio'].min(), vmax=merged_df['hawkish_ratio'].max())
mapper = cm.ScalarMappable(norm=norm, cmap=cm.coolwarm)

# Plot the bars with colors based on hawkish_ratio and wider width
ax.bar(merged_df['date'], merged_df['diff_pct'], color=mapper.to_rgba(merged_df['hawkish_ratio']), width=20)

# Add a colorbar
cbar = fig.colorbar(mapper, ax=ax)
cbar.set_label('Hawkish Ratio')

ax.set_xlabel('Date')
ax.set_ylabel('NASDAQ Pct Change')
plt.title('NASDAQ Pct Change on FOMC Dates, Colored by Hawkish Ratio')
plt.savefig('output/hawkish_ratio_vs_ixic_pct_barplot_wider.png')

print("Plot saved to output/hawkish_ratio_vs_ixic_pct_barplot_wider.png")