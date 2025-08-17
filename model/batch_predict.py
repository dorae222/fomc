
#!/usr/bin/env python3
"""
batch_predict.py: Recursively finds all PDFs in a directory, runs prediction,
and saves the combined results to a single CSV file.

Usage:
  python model/batch_predict.py --input_dir data/raw --output_csv output/batch_predictions.csv
"""

import argparse
import os
import pandas as pd
from pathlib import Path
from typing import List, Dict

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import pdfplumber

# Try to import spaCy; if missing, we'll raise a helpful error when user requests spaCy mode
try:
    import spacy
    _HAS_SPACY = True
except ImportError:
    _HAS_SPACY = False

# Default label ordering used in training: 0=dovish, 1=neutral, 2=hawkish
LABELS = ["dovish", "neutral", "hawkish"]


# --- Core Functions (from predict.py) ---

def extract_text_from_pdf(path: str) -> str:
    """Extracts all text from a PDF file."""
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
    except Exception as e:
        print(f"Error reading PDF {path}: {e}")
        return ""
    return "\n\n".join(texts)

def split_into_sentences_spacy(text: str, model_name="en_core_web_sm") -> List[str]:
    """Splits text into sentences using spaCy for higher accuracy."""
    if not _HAS_SPACY:
        raise RuntimeError("spaCy is not installed. Install with `pip install spacy` and `python -m spacy download en_core_web_sm`")
    nlp = spacy.load(model_name, disable=["ner", "tagger", "parser"])
    if not nlp.has_pipe("senter") and not nlp.has_pipe("sentencizer"):
        nlp.add_pipe("sentencizer")
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

def predict_texts(texts: List[str], tokenizer, model, device, batch_size=8, max_length=512) -> List[Dict]:
    """Runs model inference on a list of texts."""
    model.eval()
    results = []
    n = len(texts)
    for i in range(0, n, batch_size):
        batch_texts = texts[i:i+batch_size]
        enc = tokenizer(batch_texts, truncation=True, padding=True, max_length=max_length, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            outputs = model(**enc)
            logits = outputs.logits.cpu()
            probs = F.softmax(logits, dim=-1).cpu()
            preds = torch.argmax(probs, dim=-1).cpu()
        for j, txt in enumerate(batch_texts):
            pred = int(preds[j].item())
            pred_label = LABELS[pred] if 0 <= pred < len(LABELS) else str(pred)
            results.append({
                "id": i + j,
                "text": txt,
                "pred_label": pred_label,
                "max_prob": float(max(probs[j].tolist())),
            })
    return results

# --- Main Batch Processing Logic ---

def main():
    parser = argparse.ArgumentParser(description="Batch predict FOMC stance on all PDFs in a directory.")
    parser.add_argument("--input_dir", required=True, help="Directory to search for PDF files recursively.")
    parser.add_argument("--model_dir", default="./finbert2-fomc-classifier", help="Directory of the fine-tuned model.")
    parser.add_argument("--output_csv", required=True, help="Path to save the combined CSV results.")
    parser.add_argument("--batch_size", type=int, default=8, help="Inference batch size.")
    args = parser.parse_args()

    # Validate paths
    if not os.path.isdir(args.input_dir):
        raise FileNotFoundError(f"Input directory not found: {args.input_dir}")
    if not os.path.isdir(args.model_dir):
        raise FileNotFoundError(f"Model directory not found: {args.model_dir}. Please run training first.")

    # Load model and tokenizer once
    print(f"Loading model from {args.model_dir}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print(f"Using device: {device}")

    # Find all PDF files
    pdf_files = list(Path(args.input_dir).rglob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files to analyze.")

    all_results = []
    for pdf_path in pdf_files:
        print(f"\nProcessing: {pdf_path}...")
        text = extract_text_from_pdf(str(pdf_path))
        if not text.strip():
            print("  -> No text extracted, skipping.")
            continue
        
        sentences = split_into_sentences_spacy(text)
        sentences = [s for s in sentences if s and len(s.strip()) > 10]
        if not sentences:
            print("  -> No valid sentences found, skipping.")
            continue

        print(f"  -> Analyzing {len(sentences)} sentences...")
        results = predict_texts(sentences, tokenizer, model, device, batch_size=args.batch_size)
        
        # Add source file information to each result
        for r in results:
            r['source_file'] = os.path.relpath(pdf_path, args.input_dir)
        
        all_results.extend(results)

    # Save combined results to a single CSV
    if not all_results:
        print("\nNo results were generated. Nothing to save.")
        return

    print(f"\nCombining results from all files...")
    df = pd.DataFrame(all_results)
    
    # Reorder columns for better readability
    cols = ['source_file', 'id', 'pred_label', 'max_prob', 'text']
    df = df[[c for c in cols if c in df.columns]]
    
    # Ensure output directory exists
    output_dir = os.path.dirname(args.output_csv)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
    df.to_csv(args.output_csv, index=False, encoding='utf-8-sig')
    print(f"Successfully saved {len(df)} predictions to {args.output_csv}")

if __name__ == "__main__":
    main()
