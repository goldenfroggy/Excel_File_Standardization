"""Infer the semantic type of a column from its sample values."""

from __future__ import annotations

import re
from typing import Any

from .cleaner import parse_date, parse_number

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_PHONE = re.compile(r"^[+]?[0-9 ]{7,15}$")
_CODE = re.compile(r"^[A-Za-z0-9_.-]+$")
_DIGITS = re.compile(r"[0-9]")
_MONEY_HINT = ("đ", "₫", "$", "€", "£", "¥", "triệu", "tỷ", "ngàn", "nghìn", "vnđ")

UNKNOWN = "unknown"


def _classify(value: Any) -> str:
    if isinstance(value, bool):
        return UNKNOWN
    if isinstance(value, float) and value != value:  # NaN
        return UNKNOWN
    if isinstance(value, (int, float)):
        return "number"
    s = str(value).strip()
    if not s:
        return UNKNOWN
    low = s.lower()
    if parse_date(value) is not None:
        return "date"
    if any(h in low for h in _MONEY_HINT):
        if parse_number(s) is not None:
            return "money"
        return "money" if _DIGITS.search(s) else UNKNOWN
    if _EMAIL.match(s):
        return "email"
    if _PHONE.match(s):
        return "phone"
    if parse_number(s) is not None:
        return "number"
    if _CODE.match(s) and len(s) <= 24 and " " not in s:
        return "code"
    return "text"


def infer_column_type(values: list[Any], limit: int = 20) -> str:
    """Infer a column's type from its (non-empty) sample values."""
    vals = []
    for v in values[:limit]:
        if v is None:
            continue
        if isinstance(v, float) and v != v:  # NaN
            continue
        vals.append(v)
    if not vals:
        return UNKNOWN
    counts: dict[str, int] = {}
    for v in vals:
        t = _classify(v)
        counts[t] = counts.get(t, 0) + 1
    best, best_n = UNKNOWN, 0
    for t, n in counts.items():
        if n > best_n:
            best, best_n = t, n
    # require a clear majority to avoid noise
    if counts.get(best, 0) < max(2, len(vals) * 0.5):
        return UNKNOWN
    return best
