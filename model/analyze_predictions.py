import pandas as pd
import os

# Define file paths
input_file = '/home/cora3/workSpace/fomc_py/fomc/output/split_predictions/all_predictions.csv'
output_dir = '/home/cora3/workSpace/fomc_py/fomc/output/split_predictions'
output_file = os.path.join(output_dir, 'summary.csv')

# Create output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Define column names for the input CSV
column_names = ['file_path', 'line_number', 'stance', 'confidence', 'text']

# Process the large CSV file in chunks
chunk_size = 100000
results = {}

try:
    for chunk in pd.read_csv(input_file, header=None, names=column_names, chunksize=chunk_size, on_bad_lines='skip', sep=',', quotechar='"', engine='python'):
        # Convert confidence to numeric
        chunk['confidence'] = pd.to_numeric(chunk['confidence'], errors='coerce')
        chunk.dropna(subset=['confidence'], inplace=True)

        # Extract PDF file name from the file_path
        chunk['pdf_file'] = chunk['file_path'].apply(lambda x: os.path.basename(x) if isinstance(x, str) else 'unknown')

        for pdf_file, group in chunk.groupby('pdf_file'):
            if pdf_file not in results:
                results[pdf_file] = {
                    'total_predictions': 0,
                    'hawkish_count': 0,
                    'neutral_count': 0,
                    'dovish_count': 0,
                    'important_count': 0,
                    'super_important_count': 0,
                    'important_hawkish_count': 0,
                    'important_neutral_count': 0,
                    'important_dovish_count': 0,
                    'super_important_hawkish_count': 0,
                    'super_important_neutral_count': 0,
                    'super_important_dovish_count': 0
                }

            results[pdf_file]['total_predictions'] += len(group)
            results[pdf_file]['hawkish_count'] += (group['stance'] == 'hawkish').sum()
            results[pdf_file]['neutral_count'] += (group['stance'] == 'neutral').sum()
            results[pdf_file]['dovish_count'] += (group['stance'] == 'dovish').sum()
            
            important_sentences = group[group['confidence'] >= 0.7]
            results[pdf_file]['important_count'] += len(important_sentences)
            results[pdf_file]['important_hawkish_count'] += (important_sentences['stance'] == 'hawkish').sum()
            results[pdf_file]['important_neutral_count'] += (important_sentences['stance'] == 'neutral').sum()
            results[pdf_file]['important_dovish_count'] += (important_sentences['stance'] == 'dovish').sum()

            super_important_sentences = group[group['confidence'] >= 0.8]
            results[pdf_file]['super_important_count'] += len(super_important_sentences)
            results[pdf_file]['super_important_hawkish_count'] += (super_important_sentences['stance'] == 'hawkish').sum()
            results[pdf_file]['super_important_neutral_count'] += (super_important_sentences['stance'] == 'neutral').sum()
            results[pdf_file]['super_important_dovish_count'] += (super_important_sentences['stance'] == 'dovish').sum()

except FileNotFoundError:
    print(f"Error: Input file not found at {input_file}")
    exit()


# Convert results dictionary to a DataFrame
summary_df = pd.DataFrame.from_dict(results, orient='index')

if not summary_df.empty:
    # Calculate ratios
    summary_df['hawkish_ratio'] = summary_df['hawkish_count'] / summary_df['total_predictions']
    summary_df['neutral_ratio'] = summary_df['neutral_count'] / summary_df['total_predictions']
    summary_df['dovish_ratio'] = summary_df['dovish_count'] / summary_df['total_predictions']

    # Reorder columns
    summary_df = summary_df[[
        'total_predictions',
        'hawkish_count',
        'neutral_count',
        'dovish_count',
        'important_count',
        'important_hawkish_count',
        'important_neutral_count',
        'important_dovish_count',
        'super_important_count',
        'super_important_hawkish_count',
        'super_important_neutral_count',
        'super_important_dovish_count',
        'hawkish_ratio',
        'neutral_ratio',
        'dovish_ratio'
    ]]
    
    # Save the summary to a CSV file
    summary_df.to_csv(output_file)

    print(f"Analysis complete. Summary saved to {output_file}")
else:
    print("No data was processed. The output file was not created.")