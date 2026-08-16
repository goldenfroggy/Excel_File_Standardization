"""Data cleaning: text, dates, numbers, default values, issue reporting."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from .models import (
    FileReport,
    Issue,
    IssueSeverity,
    IssueType,
    Template,
    TemplateColumn,
)

_CURRENCY_SYMBOLS = "₫$€£¥₹"
_THOUSAND = re.compile(r"[.,\s]")
_DIGIT = re.compile(r"[0-9]")


@dataclass
class CleanRules:
    trim: bool = True
    normalize_unicode: bool = True
    case: str = "none"  # none | upper | lower | title
    output_date_format: str = "%d/%m/%Y"
    strip_currency: bool = True
    fill_defaults: bool = True

    @classmethod
    def defaults(cls) -> "CleanRules":
        return cls()


@dataclass
class CleanStats:
    cleaned_cells: int = 0
    filled_defaults: int = 0


_DATE_FORMATS = [
    "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y",
    "%Y/%m/%d", "%d/%m/%y", "%m/%d/%y", "%d-%b-%Y", "%d/%b/%Y",
    "%d %b %Y", "%Y%m%d", "%d%m%Y",
]


def clean_text(value: str, rules: CleanRules) -> str:
    s = str(value)
    if rules.normalize_unicode:
        s = unicodedata.normalize("NFKC", s)
    if rules.trim:
        s = s.strip()
    case = rules.case
    if case == "upper":
        s = s.upper()
    elif case == "lower":
        s = s.lower()
    elif case == "title":
        s = s.title()
    return s


def parse_date(value: Any) -> datetime | None:
    """Parse a value into a datetime across common Excel/string formats."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel serial date
        try:
            return datetime(1899, 12, 30) + pd.Timedelta(days=float(value)).to_pytimedelta()
        except Exception:
            return None
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"", "na", "n/a", "none", "null"}:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        # pandas fallback: handles a broad range of formats
        return pd.to_datetime(s).to_pydatetime()
    except Exception:
        return None


def parse_number(value: Any, strip_currency: bool = True) -> float | None:
    """Parse a value into a float, stripping currency/thousand separators."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if strip_currency:
        s = s.replace("đ", "").replace("₫", "")
        s = re.sub(f"\\s*[{re.escape(_CURRENCY_SYMBOLS)}]\\s*", "", s)
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace(" ", "")
    if _DIGIT.search(s) is None:
        return None
    if "," in s and "." in s:
        # Mixed separators: the last one is the decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    else:
        # Single comma = thousands (VN convention), single dot = decimal.
        s = s.replace(",", "")
    try:
        num = float(s)
    except ValueError:
        return None
    return -num if negative else num


def _clean_cell(
    value: Any,
    col: TemplateColumn,
    rules: CleanRules,
) -> tuple[Any, Issue | None]:
    """Clean a single cell based on the column's data type."""
    data_type = (col.data_type or "text").lower()

    if value is None:
        return None, None
    if isinstance(value, float) and pd.isna(value):
        return None, None

    if data_type == "date":
        dt = parse_date(value)
        if dt is None:
            return (
                value,
                Issue(0, col.name, IssueSeverity.ERROR, IssueType.BAD_FORMAT,
                      f"Không thể đọc giá trị ngày: {value!r}", value),
            )
        return dt.strftime(rules.output_date_format), None

    if data_type in {"number", "numeric", "int", "float", "money", "price"}:
        num = parse_number(value, rules.strip_currency)
        if num is None:
            return (
                value,
                Issue(0, col.name, IssueSeverity.ERROR, IssueType.BAD_FORMAT,
                      f"Không thể đọc giá trị số: {value!r}", value),
            )
        if data_type in {"int"}:
            return int(num), None
        return num, None

    # text
    text = clean_text(value, rules)
    return (text or None), None


def apply_rules(
    df: pd.DataFrame,
    template: Template,
    mappings: list[Any],
    rules: CleanRules,
    report: FileReport,
) -> CleanStats:
    """Apply cleaning rules in-place to a DataFrame, reporting issues."""
    stats = CleanStats()
    src_to_tpl = {m.source_col: m.template_col for m in mappings if m.source_col}
    tpl_cols = {c.name: c for c in template.columns}
    issues = report.issues

    # Coerce to object dtype in place so mixed types (str/float/int) can be stored.
    for col in df.columns:
        df[col] = df[col].astype(object)

    for idx, row in df.iterrows():
        for src_col, tpl_name in src_to_tpl.items():
            col_def = tpl_cols.get(tpl_name)
            if col_def is None:
                continue
            value = row.get(src_col)
            cleaned, issue = _clean_cell(value, col_def, rules)
            if issue is not None:
                issue.row = idx + 2  # 1-based accounting for header
                issues.append(issue)
            if cleaned is not None:
                if cleaned != value:
                    stats.cleaned_cells += 1
                df.at[idx, src_col] = cleaned
            else:
                df.at[idx, src_col] = None

    if rules.fill_defaults:
        for src_col, tpl_name in src_to_tpl.items():
            col_def = tpl_cols.get(tpl_name)
            if col_def is None or col_def.default_value is None:
                continue
            mask = df[src_col].isna()
            if mask.any():
                n = int(mask.sum())
                df.loc[mask, src_col] = col_def.default_value
                stats.filled_defaults += n
                for r in df.index[mask]:
                    issues.append(
                        Issue(
                            int(r) + 2,
                            tpl_name,
                            IssueSeverity.WARNING,
                            IssueType.MISSING_VALUE,
                            f"Thiếu giá trị, đã điền mặc định: {col_def.default_value!r}",
                            None,
                        )
                    )
    return stats
