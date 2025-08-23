"""Shared helpers to parse dates and document types from filenames/paths."""
import re
from datetime import datetime
from typing import Optional, Tuple

DOC_TYPE_MAP = {
    'statement': ['statement', 'policy', 'mone', 'mpstatement'],
    'minutes': ['minutes'],
    'press_conf': ['press', 'pressconf', 'press_conf', 'pressconference'],
    'transcript': ['transcript'],
    'beigebook': ['beigebook', 'beige'],
}

def extract_date(src: str) -> Optional[str]:
    """Extract a date in YYYY-MM-DD from path-like string, if possible."""
    if not src:
        return None
    # Prefer 8-digit yyyymmdd
    m = re.search(r'(19|20)\d{6}', src)
    if m:
        raw = m.group(0)
        try:
            dt = datetime.strptime(raw, '%Y%m%d')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    # Try ISO like yyyy-mm-dd
    m2 = re.search(r'(19|20)\d{2}-\d{2}-\d{2}', src)
    if m2:
        try:
            dt = datetime.strptime(m2.group(0), '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            return None
    return None

def extract_document_type(src: str) -> str:
    """Map path-like string to a normalized document type."""
    if not src:
        return 'other'
    s = src.lower()
    for key, patterns in DOC_TYPE_MAP.items():
        if any(p in s for p in patterns):
            return key
    return 'other'

def parse_source_file(src: str) -> Tuple[Optional[str], str]:
    """Return (date, document_type) from a source_file string."""
    return extract_date(src), extract_document_type(src)
