# FinBERT FOMC Stance Analysis: Training and Prediction

This document describes the two-step process for analyzing FOMC documents using a custom-trained FinBERT model:
1.  **`train_fomc.py`**: Fine-tunes a pre-trained FinBERT model on FOMC-specific data to create a specialized classifier.
2.  **`predict.py`**: Uses the newly trained classifier to predict the stance (dovish, neutral, hawkish) of new FOMC documents.

---

## Step 1: Training the Model (`train_fomc.py`)

This script handles the entire process of fine-tuning the model. It downloads a base language model (`FinBERT2-base`) and a financial benchmark dataset (`TheFinAI/finben-fomc`) from the Hugging Face Hub, trains the model on the dataset, and saves the resulting specialized classifier locally.

### Prerequisites

Ensure you have the necessary libraries installed:

```bash
pip install transformers datasets evaluate torch
```

### How to Run

To start the training process, simply run the script from the project root directory. The script requires no command-line arguments as it uses predefined sources.

```bash
python model/train_fomc.py
```

**Note:** Training can take a significant amount of time and may require a machine with a GPU for optimal performance.

### Output

Upon successful completion, the script will create a new directory named `finbert2-fomc-classifier` in your project root. This directory contains the fine-tuned model and tokenizer files, which are essential for the prediction step.

---

## Step 2: Predicting with the Trained Model (`predict.py`)

After you have trained your custom model, you can use this script to analyze any FOMC-related PDF document.

### Prerequisites

Ensure you have the necessary libraries for prediction:

```bash
pip install torch transformers pandas pdfplumber
# For the recommended sentence splitter, also install spaCy:
pip install spacy
python -m spacy download en_core_web_sm
```

### How to Run

Run the script from the project root directory, providing the path to the PDF you want to analyze. The script will automatically use the model you created in Step 1.

**Example Command:**

```bash
python model/predict.py --pdf path/to/your/fomc_document.pdf --output results/predictions.csv
```

### Key Command-Line Arguments

*   `--pdf` (required): The path to the input PDF file you want to analyze.
*   `--output`: The path where the output CSV file with detailed predictions will be saved. (Default: `predictions.csv`)
*   `--model_dir`: The directory where the trained model is located. (Default: `./finbert2-fomc-classifier`)
*   `--mode`: The method for splitting the PDF text into smaller chunks for analysis. (Default: `sentence_spacy`)
    *   `sentence_spacy`: (Recommended) Uses the spaCy library to accurately split text into sentences.
    *   `chunk_slide`: Splits text into larger, overlapping chunks. Useful for dense paragraphs without clear sentence breaks.
*   `--threshold`: The probability threshold below which a prediction is marked as 'uncertain'. (Default: `0.6`)

### Output

1.  **Console Summary**: The script will print a summary to the console, showing the percentage of dovish, neutral, and hawkish statements found in the document.
2.  **CSV File**: A detailed CSV file will be saved at the specified output path. Each row in the file corresponds to a sentence or chunk from the document and includes the predicted label, the probability of that prediction, and the original text.
