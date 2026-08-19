"""Read PDF and image files into DataFrames.

Strategy (tiered, no system dependencies required):
  PDF:
    1. pdfplumber — extracts tables from digital PDFs (fast, 0 tokens)
    2. rapidocr-onnxruntime — OCR scan PDFs (local, 0 tokens)
    3. AI vision — fallback when OCR fails or for better quality
  Image (.jpg/.png/...):
    1. rapidocr-onnxruntime — local OCR (0 tokens)
    2. AI vision — fallback
"""

from __future__ import annotations

import base64
import json
import logging
import math
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
DOC_EXTS = PDF_EXTS | IMAGE_EXTS


def is_document(path: Path) -> bool:
    return path.suffix.lower() in DOC_EXTS


# ── main entry ──────────────────────────────────────────────────────────


def read_document(path: Path, ai_config=None) -> pd.DataFrame:
    """Read a PDF or image file and return a DataFrame with detected columns."""
    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        return _read_pdf(path, ai_config)
    if ext in IMAGE_EXTS:
        return _read_image(path, ai_config)
    raise ValueError(f"Unsupported document type: {ext}")


# ── PDF ─────────────────────────────────────────────────────────────────


def _read_pdf(path: Path, ai_config=None) -> pd.DataFrame:
    # 1. Try pdfplumber (digital PDFs with selectable text/tables)
    try:
        df = _pdfplumber_extract(path)
        if df is not None and not df.empty:
            return df
    except Exception as exc:
        logger.debug("pdfplumber failed on %s: %s", path.name, exc)

    # 2. Try local OCR
    try:
        df = _ocr_pdf(path)
        if df is not None and not df.empty:
            return df
    except Exception as exc:
        logger.debug("OCR failed on %s: %s", path.name, exc)

    # 3. AI vision fallback
    if ai_config is not None and getattr(ai_config, "enabled", False):
        try:
            return _ai_extract(path, ai_config)
        except Exception as exc:
            logger.debug("AI extract failed on %s: %s", path.name, exc)

    raise ValueError(
        f"Không trích xuất được dữ liệu từ '{path.name}'. "
        f"Thử dùng PDF có text chọn được, hoặc bật AI trong cài đặt."
    )


def _pdfplumber_extract(path: Path) -> pd.DataFrame | None:
    import pdfplumber

    # Try word-based extraction first (works better for transposed tables with split cells)
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                words = page.extract_words()
                if not words:
                    continue
                
                # Group words by row (top coordinate)
                from collections import defaultdict
                rows = defaultdict(list)
                for w in words:
                    row_key = round(w['top'] / 5) * 5
                    rows[row_key].append(w)
                
                if not rows:
                    continue
                
                # Merge words on each row
                merged_rows = []
                for y in sorted(rows.keys()):
                    row_words = sorted(rows[y], key=lambda w: w['x0'])
                    merged = []
                    current = ""
                    prev_x1 = None
                    for w in row_words:
                        if prev_x1 is not None and w['x0'] - prev_x1 > 10:
                            if current:
                                merged.append(current)
                            current = w['text']
                        else:
                            current += " " + w['text'] if current else w['text']
                        prev_x1 = w['x1']
                    if current:
                        merged.append(current)
                    
                    # Filter out page markers
                    if merged and merged[0] not in ("Sheet1", "Page 1", "Page"):
                        merged_rows.append(merged)
                
                if not merged_rows:
                    continue
                
                # Find first row with multiple columns (data row)
                data_row_idx = None
                data_row = None
                for i, row in enumerate(merged_rows):
                    if len(row) >= 3:
                        data_row_idx = i
                        data_row = row
                        break
                
                if data_row_idx is None or data_row is None:
                    continue
                
                # Extract rows from data_row_idx onwards
                extracted = []
                for row in merged_rows[data_row_idx:]:
                    extracted.append(row)
                
                if len(extracted) < 2:
                    continue
                
                # Check if transposed: first column has field names
                first_col = [r[0] for r in extracted if r]
                other_col_lens = []
                max_cols = max(len(r) for r in extracted)
                for c in range(1, max_cols):
                    cnt = sum(1 for r in extracted if c < len(r) and r[c])
                    other_col_lens.append(cnt)
                
                avg_other = sum(other_col_lens) / len(other_col_lens) if other_col_lens else 0
                if len(first_col) > avg_other * 2 and len(first_col) > 2:
                    # Transposed table
                    field_names = first_col
                    records = []
                    for c in range(1, max_cols):
                        record = {}
                        for i, field in enumerate(field_names):
                            if i < len(extracted) and c < len(extracted[i]):
                                record[field] = extracted[i][c]
                        if any(v for v in record.values() if v):
                            records.append(record)
                    if records:
                        return pd.DataFrame(records)
                
                # Normal table - first row is header
                header = extracted[0]
                data = extracted[1:]
                ncols = len(header)
                data = [r[:ncols] + [None] * (ncols - len(r)) for r in data]
                return pd.DataFrame(data, columns=header)
                
    except Exception as exc:
        logger.debug("pdfplumber word-based extraction failed on %s: %s", path.name, exc)

    # Fallback to table extraction strategies
    strategies = [
        {},
        {"vertical_strategy": "text", "horizontal_strategy": "text",
         "snap_tolerance": 3, "join_tolerance": 3,
         "edge_min_length": 3, "min_words_vertical": 1, "min_words_horizontal": 1},
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "lines_strict", "horizontal_strategy": "lines_strict"},
    ]

    for strategy in strategies:
        all_rows: list[list] = []
        header: list[str] | None = None

        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables(table_settings=strategy) if strategy else page.extract_tables()
                    for table in tables:
                        if not table:
                            continue
                        if header is None:
                            header = [_clean_cell(c) for c in table[0]]
                            all_rows.extend(
                                [_clean_cell(c) for c in row] for row in table[1:]
                            )
                        else:
                            for row in table[1:]:
                                all_rows.append([_clean_cell(c) for c in row])

            if header is None or not all_rows:
                continue

            n_cols = len(header)
            if n_cols >= 2:
                col0_count = sum(1 for row in all_rows if row and row[0])
                other_col_counts = []
                for c in range(1, n_cols):
                    cnt = sum(1 for row in all_rows if c < len(row) and row[c])
                    other_col_counts.append(cnt)

                avg_other = sum(other_col_counts) / len(other_col_counts) if other_col_counts else 0
                if col0_count > avg_other * 2 and col0_count > 3:
                    field_names = [row[0] for row in all_rows if row and row[0]]
                    records = []
                    for c in range(1, n_cols):
                        record = {}
                        for i, field in enumerate(field_names):
                            if i < len(all_rows) and c < len(all_rows[i]):
                                record[field] = all_rows[i][c]
                            else:
                                record[field] = None
                        if any(v for v in record.values() if v):
                            records.append(record)
                    if records:
                        return pd.DataFrame(records)

            ncols = len(header)
            data = [row[:ncols] + [None] * (ncols - len(row)) for row in all_rows]
            return pd.DataFrame(data, columns=header)

        except Exception as exc:
            logger.debug("pdfplumber strategy %s failed on %s: %s", strategy, path.name, exc)
            continue

    return None


def _ocr_pdf(path: Path) -> pd.DataFrame | None:
    """Convert each PDF page to an image, then OCR."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError("Cần cài pdf2image cho OCR PDF: pip install pdf2image")
    images = convert_from_path(str(path))
    dfs = []
    for img in images:
        import numpy as np

        arr = np.array(img)
        df = _ocr_numpy(arr)
        if df is not None and not df.empty:
            dfs.append(df)
    if not dfs:
        return None
    if len(dfs) == 1:
        return dfs[0]
    return pd.concat(dfs, ignore_index=True)


# ── Image ───────────────────────────────────────────────────────────────


def _read_image(path: Path, ai_config=None) -> pd.DataFrame:
    # 1. Local OCR
    try:
        from PIL import Image

        img = Image.open(path)
        import numpy as np

        arr = np.array(img)
        df = _ocr_numpy(arr)
        if df is not None and not df.empty:
            return df
    except Exception as exc:
        logger.debug("OCR failed on %s: %s", path.name, exc)

    # 2. AI vision fallback
    if ai_config is not None and getattr(ai_config, "enabled", False):
        try:
            return _ai_extract(path, ai_config)
        except Exception as exc:
            logger.debug("AI extract failed on %s: %s", path.name, exc)

    raise ValueError(
        f"Không trích xuất được dữ liệu từ '{path.name}'. "
        f"Bật AI trong cài đặt hoặc kiểm tra lại chất lượng ảnh."
    )


# ── OCR core ────────────────────────────────────────────────────────────


def _ocr_numpy(img_array) -> pd.DataFrame | None:
    """Run rapidocr on a numpy image and convert to DataFrame."""
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    result, _ = ocr(img_array)
    if not result:
        return None
    return _ocr_result_to_df(result)


def _ocr_result_to_df(result: list) -> pd.DataFrame:
    """Convert rapidocr output [(bbox, text, confidence), ...] to a DataFrame.

    Table detection heuristic:
      - Group text regions by Y-coordinate → rows
      - Within each row, sort by X-coordinate
      - First row becomes column headers
      - Detect transposed tables (field names in first column)
    """
    items = []
    for bbox, text, conf in result:
        if not text or not text.strip():
            continue
        # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        x_min = min(p[0] for p in bbox)
        y_min = min(p[1] for p in bbox)
        y_max = max(p[1] for p in bbox)
        y_mid = (y_min + y_max) / 2
        items.append({"x": x_min, "y": y_mid, "h": y_max - y_min, "text": text.strip()})

    if not items:
        return None

    # Try normal table detection first
    df = _try_normal_table(items)
    if df is not None and not df.empty:
        return df

    # Try transposed table detection
    df = _try_transposed_table(items)
    if df is not None and not df.empty:
        return df

    return None


def _try_normal_table(items: list[dict]) -> pd.DataFrame | None:
    """Try to build a normal table (header row + data rows)."""
    items.sort(key=lambda it: it["y"])
    rows: list[list[dict]] = []
    current_row: list[dict] = [items[0]]
    row_tolerance = max(it["h"] for it in items) * 0.6 if items else 10

    for item in items[1:]:
        if abs(item["y"] - current_row[-1]["y"]) <= row_tolerance:
            current_row.append(item)
        else:
            rows.append(sorted(current_row, key=lambda it: it["x"]))
            current_row = [item]
    rows.append(sorted(current_row, key=lambda it: it["x"]))

    if not rows:
        return None

    # Need at least 2 rows (header + 1 data) and reasonable column count
    if len(rows) < 2 or len(rows[0]) < 2:
        return None

    # First row → headers
    header = [cell["text"] for cell in rows[0]]
    data = []
    for row in rows[1:]:
        data.append([cell["text"] for cell in row])

    if not data:
        return None

    # Pad rows to match header length
    ncols = len(header)
    data = [r[:ncols] + [None] * (ncols - len(r)) for r in data]
    return pd.DataFrame(data, columns=header)


def _try_transposed_table(items: list[dict]) -> pd.DataFrame | None:
    """Try to build a transposed table (field names in first column).

    Expected structure:
      Row 0: Field1  Value1  Value2  Value3 ...
      Row 1: Field2  Value1  Value2  Value3 ...
      Row 2: Field3  Value1  Value2  Value3 ...
    """
    if len(items) < 4:  # Need at least 2 fields + 2 values
        return None

    # Sort by X first (columns), then Y (rows)
    items.sort(key=lambda it: (it["x"], it["y"]))

    # Group by X-coordinate → columns
    cols: list[list[dict]] = []
    current_col: list[dict] = [items[0]]
    col_tolerance = max(it["h"] for it in items) * 0.8 if items else 20

    for item in items[1:]:
        if abs(item["x"] - current_col[-1]["x"]) <= col_tolerance:
            current_col.append(item)
        else:
            cols.append(sorted(current_col, key=lambda it: it["y"]))
            current_col = [item]
    cols.append(sorted(current_col, key=lambda it: it["y"]))

    # Need at least 2 columns and first column has multiple rows
    if len(cols) < 2 or len(cols[0]) < 2:
        return None

    # First column = field names (headers for transposed table)
    field_names = [cell["text"] for cell in cols[0]]
    # Remaining columns = records
    n_records = len(cols) - 1

    # Check if all value columns have same length as field names
    valid = True
    for c in cols[1:]:
        if len(c) != len(cols[0]):
            valid = False
            break
    if not valid:
        return None

    # Build DataFrame: each record is a row, fields are columns
    data = []
    for record_idx in range(n_records):
        row = {}
        for field_idx, field_name in enumerate(field_names):
            row[field_name] = cols[record_idx + 1][field_idx]["text"]
        data.append(row)

    return pd.DataFrame(data)


# ── AI vision ───────────────────────────────────────────────────────────


def _ai_extract(path: Path, ai_config) -> pd.DataFrame:
    """Send image to AI vision model and parse table from response."""
    from openai import OpenAI

    client = OpenAI(
        api_key=ai_config.api_key,
        base_url=ai_config.base_url,
        timeout=ai_config.timeout,
        max_retries=0,
    )
    img_bytes = path.read_bytes()
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "bmp": "bmp",
            "tiff": "tiff", "tif": "tiff", "webp": "webp"}.get(suffix, "png")
    b64 = base64.b64encode(img_bytes).decode()

    system = (
        "Bạn trích xuất bảng dữ liệu từ ảnh. "
        "Phản hồi CHỈ LÀ JSON array, mỗi phần tử là object với keys là tên cột. "
        "Ví dụ: [{\"STT\":\"1\",\"Tên\":\"An\",\"Số tiền\":\"100\"}]. "
        "Không giải thích, không tiêu đề, không backtick."
    )
    resp = client.chat.completions.create(
        model=ai_config.model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": system},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/{mime};base64,{b64}"
                }},
            ],
        }],
        temperature=0.0,
        max_tokens=1000,
    )
    content = (resp.choices[0].message.content or "").strip()
    start, end = content.find("["), content.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("AI không trả về JSON array hợp lệ")
    data = json.loads(content[start:end + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("AI trả về dữ liệu rỗng")
    return pd.DataFrame(data)


# ── helpers ──────────────────────────────────────────────────────────────


def _clean_cell(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
