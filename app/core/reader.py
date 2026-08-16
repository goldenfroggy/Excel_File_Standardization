"""File reading across XLSX / XLS / CSV with automatic header-row and sheet
detection for real-world files (banner rows, merged cells, multiple sheets)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

SUPPORTED_EXTS = {".xlsx", ".xlsm", ".xls", ".csv"}
DEFAULT_MAX_SCAN = 15
HEAD_ROWS = 60


def _engine_for(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    if suffix == ".xls":
        return "xlrd"
    if suffix == ".csv":
        return "python"
    return None


def list_sheets(path: Path) -> list[str]:
    """List sheet names of an Excel workbook."""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        try:
            return pd.ExcelFile(path).sheet_names
        except Exception:
            return ["Sheet1"]
    return ["CSV"]


def _read_head(path: Path, sheet_name: str | None, n: int = HEAD_ROWS) -> pd.DataFrame:
    """Read only the first ``n`` rows as raw values (header=None)."""
    engine = _engine_for(path)
    if engine is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(
            path, engine="python", encoding="utf-8-sig", dtype=object,
            header=None, nrows=n, on_bad_lines="skip",
        )
    else:
        df = pd.read_excel(
            path, sheet_name=sheet_name or 0, dtype=object, header=None, nrows=n,
        )
    return df


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _header_score(raw: pd.DataFrame, i: int) -> float:
    """Score how much row ``i`` looks like a real header row."""
    if i >= len(raw):
        return -1.0
    row = list(raw.iloc[i].tolist())
    non_empty = [v for v in row if not _is_empty(v)]
    if len(non_empty) < 2:
        return 0.0
    filled = len(non_empty) / len(row)
    text = sum(1 for v in non_empty if isinstance(v, str)) / len(non_empty)
    distinct = len({str(v).strip() for v in non_empty}) / len(non_empty)
    score = filled * 30.0 + text * 35.0 + distinct * 25.0
    below = 0
    for j in (i + 1, i + 2):
        if j < len(raw):
            vals = [v for v in raw.iloc[j].tolist() if not _is_empty(v)]
            if vals:
                btext = sum(1 for v in vals if isinstance(v, str)) / len(vals)
                if btext < 0.85:  # rows below look like data, not another header
                    below += 10
    return score + min(below, 20)


def detect_header_row(raw: pd.DataFrame, max_scan: int = DEFAULT_MAX_SCAN) -> int:
    """Return the index of the most header-like row among the first rows."""
    best, best_score = 0, -1.0
    for i in range(min(max_scan, len(raw))):
        s = _header_score(raw, i)
        if s > best_score:
            best, best_score = i, s
    return best


def detect_transpose(raw: pd.DataFrame) -> bool:
    """Detect a transposed table (fields as rows, records as columns).

    Heuristic: the top row holds a text label in column A with mostly numeric
    cells to the right, and the first column below holds distinct text labels.
    Example:
        STT | 1 | 2 | 3 ...
        Họ tên | A | B | C ...
        Số tiền | 100 | 200 | ...
    """
    for r in range(min(3, len(raw))):
        row = raw.iloc[r].tolist()
        first, rest = row[0], row[1:]
        if _is_empty(first) or not isinstance(first, str):
            continue
        rest = [v for v in rest if not _is_empty(v)]
        if not rest:
            continue
        numeric = sum(1 for v in rest if isinstance(v, (int, float)))
        if numeric / len(rest) < 0.7:
            continue
        labels = [
            raw.iloc[j, 0]
            for j in range(r + 1, min(len(raw), r + 12))
            if not _is_empty(raw.iloc[j, 0])
        ]
        if len(labels) >= 2 and all(isinstance(l, str) for l in labels):
            distinct = {str(l).strip() for l in labels}
            if len(distinct) >= 2:
                return True
    return False


def pick_best_sheet(path: Path) -> str | None:
    """Pick the sheet that looks most like a data sheet."""
    sheets = list_sheets(path)
    if len(sheets) <= 1:
        return None
    best_name, best_score = None, -1.0
    for name in sheets:
        try:
            head = _read_head(path, name)
        except Exception:
            continue
        if head.empty:
            continue
        non_empty = int(head.notna().sum().sum())
        hdr = detect_header_row(head)
        header_ok = _header_score(head, hdr) > 55.0
        score = min(non_empty, 30) + (20.0 if header_ok else 0.0)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


def _clean_header(raw_header: list[Any]) -> list[str]:
    """Normalize a raw header row: fill merged blanks, strip text."""
    names: list[str] = []
    last = ""
    for i, v in enumerate(raw_header):
        if _is_empty(v):
            name = last if last else f"Unnamed: {i}"
        else:
            name = str(v).strip()
            last = name
        names.append(name)
    return names


def _read_full_data(
    path: Path, sheet_name: str | None, start_row: int
) -> pd.DataFrame:
    """Read all rows from ``start_row`` onward (header excluded)."""
    engine = _engine_for(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(
            path, engine="python", encoding="utf-8-sig", dtype=object,
            header=None, skiprows=start_row, on_bad_lines="skip",
        )
    return pd.read_excel(
        path, sheet_name=sheet_name or 0, dtype=object, header=None,
        skiprows=start_row,
    )


def _resolve_header(path: Path, sheet_name: str | None, header_row: int | None,
                    skip_rows: int, encoding: str) -> tuple[str, int, pd.DataFrame]:
    """Determine the header row and its raw values.

    Returns (header, header_index, raw_head). ``header_row`` wins when given,
    else ``skip_rows`` (manual override) when > 0, else auto-detection.
    """
    head = _read_head(path, sheet_name)
    if header_row is not None:
        idx = header_row
    elif skip_rows and skip_rows > 0:
        idx = skip_rows
    else:
        idx = detect_header_row(head)
    if idx >= len(head):
        idx = 0
    header = _clean_header(list(head.iloc[idx].tolist()))
    return sheet_name, idx, head


def read_frame_head(
    path: Path,
    sheet_name: str | None = None,
    skip_rows: int = 0,
    header_row: int | None = None,
    encoding: str = "utf-8-sig",
) -> list[str]:
    """Return the header row (column names) of a file."""
    head = _read_head(path, sheet_name)
    if detect_transpose(head):
        trans = _read_transposed(path, sheet_name)
        return list(trans.columns)
    _, idx, head = _resolve_header(path, sheet_name, header_row, skip_rows, encoding)
    return _clean_header(list(head.iloc[idx].tolist()))


def _read_transposed(path: Path, sheet_name: str | None) -> pd.DataFrame:
    """Read a transposed table: fields as rows -> columns, records as columns -> rows."""
    data = _read_full_data(path, sheet_name, 0)
    t = data.T.reset_index(drop=True)
    header = _clean_header(list(t.iloc[0].tolist()))
    t = t.iloc[1:].reset_index(drop=True)
    ncols = min(len(header), t.shape[1])
    t = t.iloc[:, :ncols]
    t.columns = header[:ncols]
    for col in t.columns:
        t[col] = t[col].astype(object)
    return t


def read_frame(
    path: Path,
    sheet_name: str | None = None,
    skip_rows: int = 0,
    header_row: int | None = None,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """Read a file into a DataFrame using the detected header row."""
    head = _read_head(path, sheet_name)
    if detect_transpose(head):
        return _read_transposed(path, sheet_name)
    sheet, idx, head = _resolve_header(path, sheet_name, header_row, skip_rows, encoding)
    header = _clean_header(list(head.iloc[idx].tolist()))
    data = _read_full_data(path, sheet, idx + 1)
    data = data.reset_index(drop=True)
    ncols = min(len(header), data.shape[1])
    data = data.iloc[:, :ncols]
    data.columns = header[:ncols]
    for col in data.columns:
        data[col] = data[col].astype(object)
    data.columns = [f"Unnamed: {i}" if c == "" else c for i, c in enumerate(data.columns)]
    return data


def sample_values(
    path: Path,
    sheet_name: str | None = None,
    skip_rows: int = 0,
    header_row: int | None = None,
    limit: int = 20,
    encoding: str = "utf-8-sig",
) -> dict[str, list[Any]]:
    """Sample the first non-empty values of each column for type inference."""
    df = read_frame(path, sheet_name, skip_rows, header_row, encoding)
    samples: dict[str, list[Any]] = {}
    for col in df.columns:
        vals = [v for v in df[col].tolist() if not _is_empty(v)]
        samples[col] = vals[:limit]
    return samples
