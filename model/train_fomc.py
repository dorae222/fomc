# train_fomc.py
"""
Robust FinBERT2 fine-tuning script for TheFinAI/finben-fomc dataset.
- Auto-detects label column (gold/answer/labels/label/choices)
- Maps textual labels (dovish/hawkish/neutral) -> ints (0/2/1)
- If dataset has single split, creates train/validation/test splits
- Handles older/newer transformers TrainingArguments signatures
- Trains and saves model to ./finbert2-fomc-classifier
"""

import os
import inspect
import logging
from datasets import load_dataset, Dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)
import evaluate
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = "valuesimplex-ai-lab/FinBERT2-base"
OUTPUT_DIR = "./results"
SAVE_DIR = "./finbert2-fomc-classifier"
MAX_LENGTH = 512
NUM_LABELS = 3  # dovish=0, neutral=1, hawkish=2
SEED = 42


def make_training_args(output_dir=OUTPUT_DIR):
    common_kwargs = {
        "output_dir": output_dir,
        "num_train_epochs": 4,
        "per_device_train_batch_size": 8,
        "per_device_eval_batch_size": 8,
        "learning_rate": 2e-5,
        "weight_decay": 0.01,
        "logging_dir": "./logs",
        "logging_steps": 50,
        "seed": SEED,
        "fp16": torch.cuda.is_available(),  # use mixed precision if GPU available
    }
    sig = inspect.signature(TrainingArguments)
    params = sig.parameters
    if "evaluation_strategy" in params:
        common_kwargs.update({
            "evaluation_strategy": "epoch",
            "save_strategy": "epoch",
            "load_best_model_at_end": True,
            "save_total_limit": 3,
        })
    else:
        # older transformers
        common_kwargs.update({
            "do_eval": True,
            "save_steps": 500,
            "save_total_limit": 3,
        })
    return TrainingArguments(**common_kwargs)


def detect_label_column(ds: DatasetDict):
    """
    Return the best label column name from dataset splits.
    Checks common names: labels, label, gold, answer, choices, target, class, y
    """
    # pick a split to inspect (prefer train/validation/test)
    for pref in ("train", "validation", "test"):
        if pref in ds:
            inspect_split = pref
            break
    else:
        inspect_split = list(ds.keys())[0]

    cols = ds[inspect_split].column_names
    logger.info(f"Inspecting columns in split '{inspect_split}': {cols}")

    candidates = ["labels", "label", "gold", "answer", "choices", "target", "class", "y"]
    for c in candidates:
        if c in cols:
            logger.info(f"Detected label column: {c}")
            return c
    # fallback: look for small set of non-text columns
    for c in cols:
        if c.lower() in ("ans", "result"):
            return c
    raise ValueError(f"Could not find a label-like column in columns: {cols}")


def textual_label_to_int(s: str):
    """Map textual label to integer (dovish=0, neutral=1, hawkish=2)."""
    if s is None:
        return 1
    st = str(s).lower().strip()
    # numeric string
    if st.isdigit():
        try:
            return int(st)
        except:
            pass
    # common patterns
    if "dov" in st or "dove" in st:
        return 0
    if "hawk" in st:
        return 2
    if "neut" in st or "neutral" in st:
        return 1
    # sometimes choices like "DOVISH|NEUTRAL" or "A) DOVISH"
    tokens = st.replace("|", " ").replace("/", " ").split()
    for t in tokens:
        if "dov" in t:
            return 0
        if "hawk" in t:
            return 2
        if "neut" in t:
            return 1
    # fallback: neutral
    return 1


def map_label_batch(examples, label_col):
    vals = examples[label_col]
    mapped = [textual_label_to_int(v) for v in vals]
    return {"labels": mapped}


def ensure_train_val_test(ds: DatasetDict):
    """Ensure dataset has train/validation/test splits. If only one split present, create them."""
    keys = list(ds.keys())
    logger.info(f"Dataset splits present: {keys}")
    if "train" in ds and ("validation" in ds or "test" in ds):
        # OK
        if "validation" not in ds and "test" in ds:
            # create validation from test if needed
            tmp = ds["test"].train_test_split(test_size=0.5, seed=SEED)
            ds["validation"] = tmp["train"]
            ds["test"] = tmp["test"]
        return ds

    # If only one split (like 'test') or no train, create splits
    # Take the first split and split into train/val/test (80/10/10)
    base_split = ds[keys[0]]
    logger.info(f"Creating train/validation/test from single split '{keys[0]}' (80/10/10)")
    t1 = base_split.train_test_split(test_size=0.2, seed=SEED)
    train_ds = t1["train"]
    rest = t1["test"]
    t2 = rest.train_test_split(test_size=0.5, seed=SEED)
    val_ds = t2["train"]
    test_ds = t2["test"]
    new = DatasetDict({"train": train_ds, "validation": val_ds, "test": test_ds})
    return new


def main():
    # 1) load dataset
    logger.info("Loading dataset TheFinAI/finben-fomc ... (may require HF login if private)")
    dataset = load_dataset("TheFinAI/finben-fomc")

    # Wrap single Dataset into DatasetDict if necessary
    if isinstance(dataset, Dataset):
        dataset = DatasetDict({"train": dataset})

    # Ensure we have train/validation/test
    dataset = ensure_train_val_test(dataset)

    # 2) detect label column
    label_col = detect_label_column(dataset)

    # 3) quick inspect unique values (sample)
    try:
        unique_vals = dataset["train"].unique(label_col)
    except Exception:
        # fallback: sample
        sample = dataset["train"][label_col][:2000]
        unique_vals = sorted(list(set(sample)))
    logger.info(f"Sample unique values for label column ({label_col}): {unique_vals[:30]}")

    # 4) map textual labels -> integer labels in 'labels' column
    logger.info(f"Mapping '{label_col}' -> integer 'labels' ...")
    dataset = dataset.map(lambda ex: map_label_batch(ex, label_col), batched=True)

    # 5) remove old label column (if not 'labels')
    if label_col != "labels":
        try:
            dataset = dataset.remove_columns([label_col])
        except Exception:
            # ignore if cannot remove
            pass

    # 6) tokenize
    logger.info("Loading tokenizer: %s", MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=True)

    def preprocess_fn(examples):
        return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=MAX_LENGTH)

    logger.info("Tokenizing dataset (this may take a while) ...")
    remove_cols = [c for c in dataset["train"].column_names if c not in ("text", "labels")]
    tokenized = dataset.map(preprocess_fn, batched=True, remove_columns=remove_cols)

    # 7) set torch format
    tokenized.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

    # 8) load model (try safetensors)
    try:
        logger.info("Loading model with use_safetensors=True (if supported)...")
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=NUM_LABELS, use_safetensors=True)
    except TypeError:
        logger.info("use_safetensors not supported in this transformers version: loading without it.")
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=NUM_LABELS)
    except Exception as e:
        logger.warning("Model load with use_safetensors raised exception: %s. Retrying without it.", e)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=NUM_LABELS)

    # 9) metrics
    acc_metric = evaluate.load("accuracy")
    f1_metric = evaluate.load("f1")

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = logits.argmax(axis=-1)
        return {
            "accuracy": acc_metric.compute(predictions=preds, references=labels)["accuracy"],
            "f1_micro": f1_metric.compute(predictions=preds, references=labels, average="micro")["f1"],
            "f1_macro": f1_metric.compute(predictions=preds, references=labels, average="macro")["f1"],
        }

    # 10) training args and trainer
    training_args = make_training_args(output_dir=OUTPUT_DIR)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized.get("validation", None) or tokenized["train"].select(range(min(500, len(tokenized["train"])))),
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    # 11) train
    logger.info("Starting training ...")
    trainer.train()

    # 12) final evaluation on test
    if "test" in tokenized:
        logger.info("Running final evaluation on test split ...")
        results = trainer.evaluate(tokenized["test"])
    else:
        results = trainer.evaluate(tokenized["validation"])
    logger.info("Evaluation results: %s", results)

    # 13) save model + tokenizer
    os.makedirs(SAVE_DIR, exist_ok=True)
    trainer.save_model(SAVE_DIR)
    tokenizer.save_pretrained(SAVE_DIR)
    logger.info("Saved model and tokenizer to: %s", SAVE_DIR)


if __name__ == "__main__":
    main()
