cat > debug_plots_full.py <<'PY'
#!/usr/bin/env python3
# debug_plots_full.py
# Run from project root: python debug_plots_full.py

import os, glob, csv, re
PROJECT_ROOT = os.path.abspath(".")
PLOTS_DIR = os.path.join(PROJECT_ROOT, "web", "plots")
SEARCH_DIRS = [
    os.path.join(PROJECT_ROOT, "predicted", "statement_txt"),
    os.path.join(PROJECT_ROOT, "predicted", "blocks_pres_txt"),
    os.path.join(PROJECT_ROOT, "predicted", "csv"),
    os.path.join(PROJECT_ROOT, "predicted", "txt_pred"),
    os.path.join(PROJECT_ROOT, "results", "csv"),
    os.path.join(PROJECT_ROOT, "results", "plots"),
]

def find_candidate_csvs(date_token):
    patterns = [
        f"*1h*{date_token}*.csv",
        f"*{date_token}*1h*.csv",
        f"*{date_token}*ET*.csv",
        f"*{date_token}*.csv",
    ]
    out = []
    for d in SEARCH_DIRS:
        if not os.path.isdir(d):
            continue
        for pat in patterns:
            found = sorted(glob.glob(os.path.join(d, pat)))
            for fpath in found:
                if fpath not in out:
                    out.append(fpath)
    return out

num_re = re.compile(r'[-+]?\(?\d{1,3}(?:[,\d]{0,})?(?:\.\d+)?\)?')

def last_two_time_closes(path):
    try:
        with open(path, "r", encoding="utf-8", newline='') as f:
            sample = f.read(8192); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            rows = [r for r in reader if r and any((c or "").strip() for c in r)]
    except Exception as e:
        return ("ERR_READ", str(e))
    if len(rows) < 2:
        return ("ERR_ROWS", len(rows))
    def ext(row):
        t = str(row[0]).strip() if len(row) >= 1 else ""
        joined = " | ".join([str(c) for c in row if (c or "").strip()])
        ms = list(num_re.finditer(joined))
        if not ms:
            return (t, None)
        s = ms[-1].group(0).replace(",", "").replace("$", "")
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        try:
            v = float(s)
        except:
            v = None
        return (t, v)
    return ext(rows[-2]), ext(rows[-1])

def read_pred_csv(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8", newline='') as f:
            sample = f.read(8192); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            headers = []
            try:
                headers = next(reader)
            except StopIteration:
                headers = []
            norm = [h.strip().lower() for h in headers]
            def find_any(cands):
                for c in cands:
                    if c in norm:
                        return norm.index(c)
                return None
            idx_pred = find_any(["pred_label", "predlabel", "pred", "label"])
            idx_text = find_any(["text", "content", "sentence", "body"])
            if idx_text is None:
                idx_text = len(headers) - 1 if headers else 0
            if idx_pred is None:
                idx_pred = 1 if len(headers) > 1 else 0
            f.seek(0)
            reader = csv.reader(f, dialect)
            try:
                next(reader)
            except:
                pass
            for row in reader:
                if not row or not any((c or "").strip() for c in row):
                    continue
                if len(row) <= max(idx_pred, idx_text):
                    row = row + [''] * (max(idx_pred, idx_text) - len(row) + 1)
                pred_raw = (row[idx_pred] or "").strip().lower() if idx_pred < len(row) else ""
                text = ",".join(row[idx_text:]).strip() if idx_text < len(row) else ""
                out.append({"pred_label": pred_raw, "text": text})
    except Exception as e:
        return ("ERR_READ", str(e))
    return out

def analyze_csv(path):
    rows = read_pred_csv(path)
    if isinstance(rows, tuple):
        return {"read_error": rows}
    stmt = [r for r in rows if re.search(r'statem|statement|성명|statement', (r.get('text') or ''), re.I)]
    press = [r for r in rows if re.search(r'press|press conference|press release|기자|기자회견|보도|press', (r.get('text') or ''), re.I)]
    hawk_stmt = sum(1 for r in stmt if 'hawk' in (r.get('pred_label') or '').lower())
    hawk_press = sum(1 for r in press if 'hawk' in (r.get('pred_label') or '').lower())
    overall_hawk = (sum(1 for r in rows if 'hawk' in (r.get('pred_label') or '').lower()) / len(rows)) if rows else None
    return {
        "n_rows": len(rows),
        "stmt_count": len(stmt),
        "press_count": len(press),
        "hawk_stmt": hawk_stmt,
        "hawk_press": hawk_press,
        "overall_hawk": overall_hawk
    }

plots = sorted(glob.glob(os.path.join(PLOTS_DIR, "*.*")))
if not plots:
    print(">> No plots in", PLOTS_DIR)
    raise SystemExit(0)

date_re = re.compile(r'(\d{4}[-_]?\d{2}[-_]?\d{2})|(\d{8})')

for p in plots:
    name = os.path.basename(p)
    m = date_re.search(name)
    token = m.group(0) if m else None
    print("---- PLOT:", name, " token:", token)
    if not token:
        print("  -> no date token. check filename.")
        continue
    cands = find_candidate_csvs(token)
    if not cands:
        print("  -> No candidate CSV found for token in search dirs.")
        for sd in SEARCH_DIRS:
            print("     ", sd)
        continue
    for c in cands:
        print("  candidate CSV:", c)
        lt = last_two_time_closes(c)
        print("    last_two_time_closes:", lt)
        info = analyze_csv(c)
        print("    csv analysis:", info)
    print("")
