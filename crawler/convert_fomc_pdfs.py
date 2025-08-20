#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOMC PDF to Text/Markdown Converter
- PDF 파일들을 텍스트/마크다운으로 변환
- 표 구조 보존
- 기존 폴더 구조 유지
- 변환 결과 manifest 생성

Usage:
  cd crawler
  
  python convert_fomc_pdfs.py --input raw --output fomc_files \
    --format markdown --max-workers 4 --resume

Dependencies:
  pip install pdfplumber PyMuPDF pandas tqdm
"""
from __future__ import annotations

import argparse, csv, json, logging, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import hashlib

import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
from tqdm import tqdm

# -----------------------------
# Config
# -----------------------------
SUPPORTED_FORMATS = ["markdown", "text", "both"]
DEFAULT_OUTPUT_FORMAT = "markdown"

# -----------------------------
# Data classes
# -----------------------------
@dataclass
class ConversionResult:
    input_path: str
    output_path: str
    doc_type: str
    year: int
    meeting_id: str
    format_type: str  # markdown, text
    original_size: int
    converted_size: int
    page_count: int
    table_count: int
    conversion_time: float
    status: str  # success, failed, skipped
    error_msg: str = ""
    sha1_original: str = ""
    sha1_converted: str = ""

# -----------------------------
# Utils
# -----------------------------
def ensure_dir(path: str):
    """디렉토리가 없으면 생성"""
    os.makedirs(path, exist_ok=True)

def safe_filename(name: str, extension: str = "") -> str:
    """안전한 파일명 생성"""
    clean = re.sub(r"[^A-Za-z0-9_\-\.]", "_", name)
    if extension and not clean.endswith(extension):
        clean = clean.rsplit(".", 1)[0] + extension
    return clean

def sha1_file(filepath: str) -> str:
    """파일의 SHA1 해시 계산"""
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except Exception:
        return ""

def sha1_text(text: str) -> str:
    """텍스트의 SHA1 해시 계산"""
    return hashlib.sha1(text.encode('utf-8')).hexdigest()

def clean_text(text: str) -> str:
    """텍스트 정리"""
    if not text:
        return ""
    # 연속된 공백과 줄바꿈 정리
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # 3개 이상 줄바꿈을 2개로
    text = re.sub(r'[ \t]+', ' ', text)  # 연속된 공백을 하나로
    text = text.strip()
    return text

# -----------------------------
# PDF Processing
# -----------------------------
def extract_text_with_pdfplumber(pdf_path: str) -> Tuple[str, List[pd.DataFrame], int]:
    """
    pdfplumber를 사용해 텍스트와 표 추출
    Returns: (전체 텍스트, 표 리스트, 페이지 수)
    """
    all_text = []
    all_tables = []
    page_count = 0
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, 1):
                # 텍스트 추출
                page_text = page.extract_text()
                if page_text:
                    all_text.append(f"\n--- Page {page_num} ---\n")
                    all_text.append(page_text)
                
                # 표 추출
                tables = page.extract_tables()
                for table_idx, table in enumerate(tables):
                    if table and len(table) > 1:  # 최소 2행 이상
                        try:
                            # 빈 행/열 제거
                            clean_table = []
                            for row in table:
                                if row and any(cell and str(cell).strip() for cell in row):
                                    clean_row = [str(cell).strip() if cell else "" for cell in row]
                                    clean_table.append(clean_row)
                            
                            if len(clean_table) > 1:
                                df = pd.DataFrame(clean_table[1:], columns=clean_table[0])
                                df.name = f"Page_{page_num}_Table_{table_idx + 1}"
                                all_tables.append(df)
                        except Exception as e:
                            logging.warning(f"Table processing error on page {page_num}: {e}")
                            continue
    
    except Exception as e:
        logging.error(f"Error processing {pdf_path} with pdfplumber: {e}")
        return "", [], 0
    
    return "\n".join(all_text), all_tables, page_count

def extract_text_with_pymupdf(pdf_path: str) -> Tuple[str, int]:
    """
    PyMuPDF를 사용해 텍스트 추출 (fallback)
    Returns: (전체 텍스트, 페이지 수)
    """
    try:
        doc = fitz.open(pdf_path)
        all_text = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            if text.strip():
                all_text.append(f"\n--- Page {page_num + 1} ---\n")
                all_text.append(text)
        
        doc.close()
        return "\n".join(all_text), len(doc)
    
    except Exception as e:
        logging.error(f"Error processing {pdf_path} with PyMuPDF: {e}")
        return "", 0

def convert_tables_to_markdown(tables: List[pd.DataFrame]) -> str:
    """표들을 마크다운 형식으로 변환"""
    if not tables:
        return ""
    
    markdown_tables = []
    for table in tables:
        try:
            # 표 제목
            table_name = getattr(table, 'name', 'Table')
            markdown_tables.append(f"\n## {table_name}\n")
            
            # pandas의 to_markdown 사용
            if hasattr(table, 'to_markdown'):
                md_table = table.to_markdown(index=False, tablefmt='github')
                markdown_tables.append(md_table)
            else:
                # fallback: 수동으로 마크다운 테이블 생성
                headers = table.columns.tolist()
                rows = table.values.tolist()
                
                # 헤더
                header_row = "| " + " | ".join(str(h) for h in headers) + " |"
                separator = "| " + " | ".join("---" for _ in headers) + " |"
                
                # 데이터 행
                data_rows = []
                for row in rows:
                    row_str = "| " + " | ".join(str(cell) if cell else "" for cell in row) + " |"
                    data_rows.append(row_str)
                
                md_table = "\n".join([header_row, separator] + data_rows)
                markdown_tables.append(md_table)
                
        except Exception as e:
            logging.warning(f"Error converting table to markdown: {e}")
            markdown_tables.append(f"\n[Table conversion error: {e}]\n")
    
    return "\n\n".join(markdown_tables)

def convert_pdf_to_text(pdf_path: str, output_format: str = "markdown") -> Tuple[str, int, int]:
    """
    PDF를 텍스트/마크다운으로 변환
    Returns: (변환된 텍스트, 페이지 수, 표 개수)
    """
    start_time = time.time()
    
    # 먼저 pdfplumber로 시도
    text, tables, page_count = extract_text_with_pdfplumber(pdf_path)
    
    # pdfplumber가 실패하면 PyMuPDF로 fallback
    if not text.strip():
        logging.warning(f"pdfplumber failed for {pdf_path}, trying PyMuPDF")
        text, page_count = extract_text_with_pymupdf(pdf_path)
        tables = []
    
    if not text.strip():
        raise ValueError("No text could be extracted from PDF")
    
    # 텍스트 정리
    text = clean_text(text)
    
    # 표 개수
    table_count = len(tables)
    
    # 포맷에 따른 출력 생성
    if output_format == "markdown":
        # 마크다운 헤더 추가
        filename = os.path.basename(pdf_path)
        content = f"# {filename}\n\n"
        content += f"*Extracted on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        content += f"*Pages: {page_count}, Tables: {table_count}*\n\n"
        content += "## Document Content\n\n"
        content += text
        
        # 표 추가
        if tables:
            content += "\n\n# Tables\n"
            content += convert_tables_to_markdown(tables)
        
        conversion_time = time.time() - start_time
        return content, page_count, table_count
    
    else:  # text format
        content = f"File: {os.path.basename(pdf_path)}\n"
        content += f"Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"Pages: {page_count}, Tables: {table_count}\n"
        content += "=" * 80 + "\n\n"
        content += text
        
        # 표를 텍스트로 추가
        if tables:
            content += "\n\n" + "=" * 40 + " TABLES " + "=" * 40 + "\n"
            for table in tables:
                table_name = getattr(table, 'name', 'Table')
                content += f"\n{table_name}:\n"
                content += str(table.to_string(index=False))
                content += "\n" + "-" * 60 + "\n"
        
        conversion_time = time.time() - start_time
        return content, page_count, table_count

# -----------------------------
# File Discovery
# -----------------------------
def find_pdf_files(input_dir: str) -> List[Tuple[str, str, str, int]]:
    """
    입력 디렉토리에서 PDF 파일들을 찾아서 반환
    Returns: List of (pdf_path, relative_path, doc_type, year)
    """
    pdf_files = []
    input_path = Path(input_dir)
    
    for pdf_file in input_path.rglob("*.pdf"):
        try:
            rel_path = pdf_file.relative_to(input_path)
            parts = rel_path.parts
            
            if len(parts) >= 3:  # doc_type/year/filename.pdf
                doc_type = parts[0]
                year = int(parts[1])
                pdf_files.append((str(pdf_file), str(rel_path), doc_type, year))
            else:
                logging.warning(f"Unexpected path structure: {rel_path}")
        except Exception as e:
            logging.warning(f"Error processing {pdf_file}: {e}")
    
    return pdf_files

# -----------------------------
# Conversion Worker
# -----------------------------
def convert_single_pdf(
    pdf_info: Tuple[str, str, str, int],
    output_dir: str,
    output_format: str,
    overwrite: bool = False
) -> ConversionResult:
    """단일 PDF 파일 변환"""
    
    pdf_path, rel_path, doc_type, year = pdf_info
    start_time = time.time()
    
    try:
        # 출력 경로 설정
        output_rel_path = rel_path.replace('.pdf', f'.{output_format}' if output_format != 'both' else '.md')
        output_path = os.path.join(output_dir, output_rel_path)
        
        # 디렉토리 생성
        ensure_dir(os.path.dirname(output_path))
        
        # 이미 존재하고 overwrite가 False면 스킵
        if os.path.exists(output_path) and not overwrite:
            return ConversionResult(
                input_path=pdf_path,
                output_path=output_path,
                doc_type=doc_type,
                year=year,
                meeting_id=os.path.basename(pdf_path).replace('.pdf', ''),
                format_type=output_format,
                original_size=os.path.getsize(pdf_path),
                converted_size=os.path.getsize(output_path),
                page_count=0,
                table_count=0,
                conversion_time=0,
                status="skipped",
                error_msg="File already exists",
                sha1_original=sha1_file(pdf_path),
                sha1_converted=sha1_file(output_path)
            )
        
        # PDF 변환
        if output_format == "both":
            # 마크다운과 텍스트 둘 다 생성
            md_content, page_count, table_count = convert_pdf_to_text(pdf_path, "markdown")
            txt_content, _, _ = convert_pdf_to_text(pdf_path, "text")
            
            # 파일 저장
            md_path = output_path  # .md
            txt_path = output_path.replace('.md', '.txt')
            
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(txt_content)
                
            converted_size = os.path.getsize(md_path) + os.path.getsize(txt_path)
            sha1_converted = sha1_text(md_content + txt_content)
            
        else:
            # 단일 포맷
            content, page_count, table_count = convert_pdf_to_text(pdf_path, output_format)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            converted_size = os.path.getsize(output_path)
            sha1_converted = sha1_text(content)
        
        conversion_time = time.time() - start_time
        
        return ConversionResult(
            input_path=pdf_path,
            output_path=output_path,
            doc_type=doc_type,
            year=year,
            meeting_id=os.path.basename(pdf_path).replace('.pdf', ''),
            format_type=output_format,
            original_size=os.path.getsize(pdf_path),
            converted_size=converted_size,
            page_count=page_count,
            table_count=table_count,
            conversion_time=conversion_time,
            status="success",
            sha1_original=sha1_file(pdf_path),
            sha1_converted=sha1_converted
        )
        
    except Exception as e:
        conversion_time = time.time() - start_time
        logging.error(f"Conversion failed for {pdf_path}: {e}")
        
        return ConversionResult(
            input_path=pdf_path,
            output_path="",
            doc_type=doc_type,
            year=year,
            meeting_id=os.path.basename(pdf_path).replace('.pdf', ''),
            format_type=output_format,
            original_size=os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
            converted_size=0,
            page_count=0,
            table_count=0,
            conversion_time=conversion_time,
            status="failed",
            error_msg=str(e),
            sha1_original=sha1_file(pdf_path),
            sha1_converted=""
        )

# -----------------------------
# Manifest Management
# -----------------------------
def load_existing_conversions(manifest_path: str) -> Set[str]:
    """기존 변환 결과에서 성공한 파일들 로드"""
    existing = set()
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        existing.add(row.get('input_path', ''))
        except Exception as e:
            logging.warning(f"Error loading existing manifest: {e}")
    return existing

def save_conversion_result(manifest_path: str, result: ConversionResult):
    """변환 결과를 CSV에 저장"""
    file_exists = os.path.exists(manifest_path)
    
    with open(manifest_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'input_path', 'output_path', 'doc_type', 'year', 'meeting_id',
            'format_type', 'original_size', 'converted_size', 'page_count',
            'table_count', 'conversion_time', 'status', 'error_msg',
            'sha1_original', 'sha1_converted', 'timestamp'
        ])
        
        if not file_exists:
            writer.writeheader()
        
        row = asdict(result)
        row['timestamp'] = datetime.now().isoformat()
        writer.writerow(row)

# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Convert FOMC PDFs to text/markdown")
    parser.add_argument("--input", required=True, help="Input directory containing PDFs")
    parser.add_argument("--output", default="fomc_files", help="Output directory")
    parser.add_argument("--format", choices=SUPPORTED_FORMATS, default=DEFAULT_OUTPUT_FORMAT,
                       help="Output format: markdown, text, or both")
    parser.add_argument("--max-workers", type=int, default=4, help="Number of concurrent workers")
    parser.add_argument("--resume", action="store_true", help="Skip already converted files")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    parser.add_argument("--doc-types", nargs="*", default=None,
                       help="Filter by document types: statement minutes beigebook transcript tealbook framework")
    parser.add_argument("--years", default=None, help="Year range filter, e.g., 2010-2020 or 2015,2018,2020")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    
    args = parser.parse_args()
    
    # 로깅 설정
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s | %(levelname)s | %(message)s'
    )
    
    # 출력 디렉토리 생성
    ensure_dir(args.output)
    
    # Manifest 파일 경로
    manifest_path = os.path.join(args.output, "conversion_manifest.csv")
    
    # PDF 파일 검색
    logging.info(f"Scanning for PDF files in {args.input}")
    pdf_files = find_pdf_files(args.input)
    
    # 필터링
    if args.doc_types:
        allowed_types = set(t.lower() for t in args.doc_types)
        pdf_files = [f for f in pdf_files if f[2] in allowed_types]
    
    if args.years:
        # 연도 파싱
        allowed_years = set()
        for part in args.years.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                allowed_years.update(range(start, end + 1))
            else:
                allowed_years.add(int(part))
        pdf_files = [f for f in pdf_files if f[3] in allowed_years]
    
    logging.info(f"Found {len(pdf_files)} PDF files to process")
    
    # Resume 기능
    if args.resume:
        existing = load_existing_conversions(manifest_path)
        before_count = len(pdf_files)
        pdf_files = [f for f in pdf_files if f[0] not in existing]
        logging.info(f"Resume: skipped {before_count - len(pdf_files)} already converted files")
    
    if not pdf_files:
        logging.info("No files to process")
        return
    
    # 변환 실행
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_original_size = 0
    total_converted_size = 0
    total_pages = 0
    total_tables = 0
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # 작업 제출
        futures = {
            executor.submit(convert_single_pdf, pdf_info, args.output, args.format, args.overwrite): pdf_info
            for pdf_info in pdf_files
        }
        
        # 진행상황 표시
        for future in tqdm(as_completed(futures), total=len(futures), desc="Converting PDFs"):
            result = future.result()
            
            # 결과 저장
            save_conversion_result(manifest_path, result)
            
            # 통계 업데이트
            if result.status == "success":
                success_count += 1
                total_original_size += result.original_size
                total_converted_size += result.converted_size
                total_pages += result.page_count
                total_tables += result.table_count
            elif result.status == "failed":
                failed_count += 1
            elif result.status == "skipped":
                skipped_count += 1
            
            # 에러 로깅
            if result.status == "failed":
                logging.error(f"Failed to convert {result.input_path}: {result.error_msg}")
    
    # 최종 요약
    logging.info("=" * 60)
    logging.info("FOMC PDF Conversion Summary")
    logging.info(f"Total files processed: {len(pdf_files)}")
    logging.info(f"Successfully converted: {success_count}")
    logging.info(f"Failed: {failed_count}")
    logging.info(f"Skipped: {skipped_count}")
    logging.info(f"Total pages processed: {total_pages}")
    logging.info(f"Total tables extracted: {total_tables}")
    logging.info(f"Original size: {total_original_size / 1024 / 1024:.2f} MB")
    logging.info(f"Converted size: {total_converted_size / 1024 / 1024:.2f} MB")
    logging.info(f"Output directory: {args.output}")
    logging.info(f"Conversion manifest: {manifest_path}")
    logging.info("Done!")

if __name__ == "__main__":
    main()