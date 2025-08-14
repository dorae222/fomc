#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit manifest produced by fetch_fomc_pdfs.py
- Prints counts by year/type, year×type pivot
- Flags suspicious dates: Jan 1 default, future dates
- Flags transcripts within last 5 years (should be rare due to lag)
- Finds SHA1 duplicates (same file different path)
"""

import pandas as pd
from datetime import date

MANIFEST = r"./data/raw/manifest.csv"
TODAY = date.today()

def main():
    m = pd.read_csv(MANIFEST, dtype=str, keep_default_na=False)

    # Normalize types/years
    m["doc_type"] = m["doc_type"].str.lower()
    m["year"] = pd.to_numeric(m["year"], errors="coerce").fillna(0).astype(int)

    # Parse date_guess as datetime (UTC-naive)
    m["date_guess"] = pd.to_datetime(m["date_guess"], errors="coerce")

    print("\n[요약]")
    print("총 행:", len(m))
    print("\n유형별 개수:\n", m["doc_type"].value_counts().sort_index())
    print("\n연도별 개수:\n", m["year"].value_counts().sort_index())

    # Pivot
    pv = pd.pivot_table(m, index="year", columns="doc_type", values="saved_path",
                        aggfunc="count", fill_value=0).sort_index()
    print("\n연도 × 유형 매트릭스:\n", pv.tail(40))

    # Jan 1 flags (if day/month are exactly 1)
    jan1 = m[m["date_guess"].notna() & (m["date_guess"].dt.month == 1) & (m["date_guess"].dt.day == 1)]
    print(f"\n의심(1월 1일 날짜): {len(jan1)}건")
    if not jan1.empty:
        print(jan1[["saved_path","doc_type","date_guess","source_url"]].head(15).to_string(index=False))

    # Future dates
    future = m[m["date_guess"].notna() & (m["date_guess"].dt.date > TODAY)]
    print(f"\n의심(미래 날짜): {len(future)}건")
    if not future.empty:
        print(future[["saved_path","doc_type","date_guess","source_url"]].head(15).to_string(index=False))

    # Recent transcripts (within 5y)
    recent_trans = m[(m["doc_type"]=="transcript") & m["date_guess"].notna() &
                     ((TODAY.year - m["date_guess"].dt.year) < 5)]
    print(f"\n의심(최근 5년 내 transcript): {len(recent_trans)}건")
    if not recent_trans.empty:
        print(recent_trans[["saved_path","date_guess","source_url"]].head(15).to_string(index=False))

    # SHA1 duplicates
    if "sha1" in m.columns:
        dup = m[(m["sha1"]!="") & m["sha1"].duplicated(keep=False)].sort_values("sha1")
        print(f"\nSHA1 중복 파일 개수: {dup['sha1'].nunique()} 세트 / 행 {len(dup)}")
        if not dup.empty:
            print(dup[["sha1","saved_path","source_url"]].head(20).to_string(index=False))

if __name__ == "__main__":
    main()
