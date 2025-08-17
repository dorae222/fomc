#!/usr/bin/env python3
"""
predict.py - Enhanced version with spaCy sentence splitting, sliding-window token chunking, and uncertainty thresholding.

Usage examples:
  python predict.py --pdf docs/fomc.pdf --mode sentence_spacy --model_dir ./finbert2-fomc-classifier --output preds.csv
  python predict.py --pdf docs/fomc.pdf --mode chunk_slide --max_length 512 --overlap 128 --batch_size 8 --threshold 0.6
"""

import argparse
import os
import json
import csv
import re
from typing import List

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import pdfplumber
import pandas as pd

# Try to import spaCy; if missing, we'll raise a helpful error when user requests spaCy mode
try:
    import spacy
    _HAS_SPACY = True
except Exception:
    _HAS_SPACY = False

# Default label ordering used in training: 0=dovish, 1=neutral, 2=hawkish
LABELS = ["dovish", "neutral", "hawkish"]


def extract_text_from_pdf(path: str) -> str:
    texts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
    return "\n\n".join(texts)


def split_into_sentences_regex(text: str) -> List[str]:
    # Basic regex-based sentence splitter (fast, but less accurate)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    sentences = []
    sentence_end_re = re.compile(r'(?<=[\.\?\!])\s+(?=[A-Z0-9“"\'(])')
    for p in paragraphs:
        parts = sentence_end_re.split(p)
        for s in parts:
            s = s.strip()
            if s:
                sentences.append(s)
    if not sentences:
        sentences = [line.strip() for line in text.splitlines() if line.strip()]
    return sentences


def split_into_sentences_spacy(text: str, model_name="en_core_web_sm") -> List[str]:
    if not _HAS_SPACY:
        raise RuntimeError("spaCy is not installed. Install with `pip install spacy` and `python -m spacy download en_core_web_sm`")
    nlp = spacy.load(model_name, disable=["ner", "tagger", "parser"])
    # Enable sentencizer if not present
    if not nlp.has_pipe("senter") and not nlp.has_pipe("sentencizer"):
        nlp.add_pipe("sentencizer")
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    return sentences


def chunk_text_by_tokens(text: str, tokenizer, max_length=512, overlap=0, stride_mode=False) -> List[str]:
    """
    Create token-based chunks of text.
    - If stride_mode=False: non-overlapping windows of size max_length
    - If stride_mode=True: sliding windows with overlap specified (0 <= overlap < max_length)
    Returns list of decoded chunk strings.
    """
    if max_length <= 0:
        raise ValueError("max_length must be > 0")
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) == 0:
        return []
    chunks = []
    if not stride_mode or overlap <= 0:
        # simple non-overlap windows
        for i in range(0, len(token_ids), max_length):
            window = token_ids[i:i+max_length]
            decoded = tokenizer.decode(window, skip_special_tokens=True, clean_up_tokenization_spaces=True).strip()
            if decoded:
                chunks.append(decoded)
    else:
        stride = max_length - overlap
        if stride <= 0:
            raise ValueError("overlap must be smaller than max_length")
        for i in range(0, len(token_ids), stride):
            window = token_ids[i:i+max_length]
            decoded = tokenizer.decode(window, skip_special_tokens=True, clean_up_tokenization_spaces=True).strip()
            if decoded:
                chunks.append(decoded)
            if i + max_length >= len(token_ids):
                break
    return chunks


def predict_texts(texts: List[str], tokenizer, model, device, batch_size=8, max_length=512, threshold=0.6):
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
            idx = i + j
            logit = logits[j].tolist()
            prob = probs[j].tolist()
            pred = int(preds[j].item())
            max_prob = float(max(prob))
            uncertain = bool(max_prob < threshold)
            pred_label = LABELS[pred] if 0 <= pred < len(LABELS) else str(pred)
            results.append({
                "id": idx,
                "text": txt,
                "pred": pred,
                "pred_label": pred_label,
                "logits": logit,
                "probs": prob,
                "max_prob": max_prob,
                "uncertain": uncertain
            })
    return results


def save_results_csv(results: List[dict], out_path: str):
    df = pd.DataFrame(results)
    # Keep columns in a friendly order
    cols = ["id", "pred_label", "pred", "max_prob", "uncertain", "probs", "logits", "text"]
    df = df[cols]
    df.to_csv(out_path, index=False, encoding="utf-8")


def summarize_results(results: List[dict], threshold=0.6):
    total = len(results)
    counts = {}
    uncertain_count = 0
    for r in results:
        counts[r["pred_label"]] = counts.get(r["pred_label"], 0) + 1
        if r["uncertain"]:
            uncertain_count += 1
    print("Prediction summary:")
    for k in sorted(counts.keys()):
        print(f"  {k}: {counts[k]} ({counts[k]/total*100:.1f}%)")
    print(f"Total items: {total}")
    print(f"Uncertain (max_prob < {threshold}): {uncertain_count} ({uncertain_count/total*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Predict dovish/neutral/hawkish on PDFs with advanced splitting and uncertainty")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--mode", choices=["sentence_spacy", "sentence_regex", "chunk", "chunk_slide", "page"], default="sentence_spacy", help="split mode")
    parser.add_argument("--max_length", type=int, default=512, help="max tokens for chunking / tokenizer")
    parser.add_argument("--overlap", type=int, default=0, help="overlap tokens for chunk_slide")
    parser.add_argument("--batch_size", type=int, default=8, help="inference batch size")
    parser.add_argument("--model_dir", default="./finbert2-fomc-classifier", help="directory of fine-tuned model/tokenizer")
    parser.add_argument("--output", default="predictions.csv", help="output CSV path")
    parser.add_argument("--threshold", type=float, default=0.6, help="uncertainty threshold for max_prob")
    args = parser.parse_args()

    pdf_path = args.pdf
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if not os.path.isdir(args.model_dir):
        raise FileNotFoundError(f"Model dir not found: {args.model_dir}. Make sure the fine-tuned model exists here.")

    print("Loading tokenizer and model from:", args.model_dir)
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, use_fast=True)
    try:
        model = AutoModelForSequenceClassification.from_pretrained(args.model_dir, use_safetensors=True)
    except TypeError:
        model = AutoModelForSequenceClassification.from_pretrained(args.model_dir)
    except Exception as e:
        print("Warning: model load with use_safetensors raised:", e)
        model = AutoModelForSequenceClassification.from_pretrained(args.model_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print("Device:", device)

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise ValueError("No text extracted from PDF (maybe scanned images).")

    items = []
    if args.mode == "page":
        with pdfplumber.open(pdf_path) as pdf:
            for p_idx, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                t = t.strip()
                if t:
                    items.append(t)
    elif args.mode == "sentence_regex":
        items = split_into_sentences_regex(text)
    elif args.mode == "sentence_spacy":
        if not _HAS_SPACY:
            raise RuntimeError("spaCy is not installed. Install it: pip install spacy && python -m spacy download en_core_web_sm")
        items = split_into_sentences_spacy(text)
    elif args.mode == "chunk":
        items = chunk_text_by_tokens(text, tokenizer, max_length=args.max_length, overlap=0, stride_mode=False)
    elif args.mode == "chunk_slide":
        if args.overlap <= 0:
            raise ValueError("For chunk_slide, please set --overlap > 0 (for example 128)")
        items = chunk_text_by_tokens(text, tokenizer, max_length=args.max_length, overlap=args.overlap, stride_mode=True)
    else:
        raise ValueError("Unknown mode")

    print(f"Prepared {len(items)} items for prediction (mode={args.mode}). Filtering empty/short items...")
    items = [it for it in items if it and len(it.strip()) > 5]
    print(f"{len(items)} items remain after filtering.")

    results = predict_texts(items, tokenizer, model, device, batch_size=args.batch_size, max_length=args.max_length, threshold=args.threshold)
    save_results_csv(results, args.output)
    print("Saved predictions to:", args.output)
    summarize_results(results, threshold=args.threshold)


if __name__ == "__main__":
    main()
