"""Column matching v2: combined scoring over name similarity, word overlap,
data-type agreement and an editable synonym dictionary.

Pipeline stays token-economical: everything here runs locally (0 tokens); AI is
only consulted later for columns still unmatched (see ai_matcher).
"""

from __future__ import annotations

import unicodedata
from typing import Any

from rapidfuzz import fuzz

from .models import ColumnMapping, MatchSource

DEFAULT_THRESHOLD = 60.0

_TYPE_GROUPS = {
    "text": {"text", "code", "email", "phone", "unknown"},
    "code": {"code", "text", "unknown"},
    "email": {"email", "unknown"},
    "phone": {"phone", "unknown"},
    "date": {"date", "unknown"},
    "number": {"number", "money", "int", "unknown"},
    "int": {"int", "number", "money", "unknown"},
    "money": {"money", "number", "int", "unknown"},
}


def normalize(name: str) -> str:
    """Normalize a header string for comparison (accent folding + strip)."""
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(s.split())


def _tokens(norm: str) -> set[str]:
    return set(norm.split())


def _name_score(a: str, b: str) -> float:
    return max(
        fuzz.ratio(a, b),
        fuzz.token_set_ratio(a, b),
        fuzz.token_sort_ratio(a, b),
    )


def _token_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb) * 100.0


def _type_bonus(template_type: str | None, source_type: str | None) -> float:
    if not template_type or not source_type or source_type == "unknown":
        return 0.0
    group = _TYPE_GROUPS.get(template_type.lower())
    if group is None:
        return 0.0
    return 15.0 if source_type in group else -12.0


def score_pair(
    tcol: str,
    scol: str,
    template_type: str | None = None,
    source_type: str | None = None,
    synonyms: Any = None,
) -> float:
    """Combined 0..100 match score for a template/source column pair."""
    nt, ns = normalize(tcol), normalize(scol)
    if synonyms is not None and ns in synonyms.aliases(tcol):
        return 100.0
    name = _name_score(nt, ns)
    tokens = _token_overlap(nt, ns)
    bonus = _type_bonus(template_type, source_type)
    score = name * 0.55 + tokens * 0.30 + bonus
    return max(0.0, min(100.0, score))


def match_columns(
    template_cols: list[str],
    source_cols: list[str],
    threshold: float = DEFAULT_THRESHOLD,
    template_types: dict[str, str] | None = None,
    source_samples: dict[str, list[Any]] | None = None,
    synonyms: Any = None,
) -> list[ColumnMapping]:
    """Suggest the best source column for each template column.

    Each source column is used at most once. A template column with no source
    column above ``threshold`` stays unmapped (may be resolved by AI later).
    """
    from .type_inference import infer_column_type

    template_types = template_types or {}
    if source_samples is None:
        source_samples = {}
    source_types = {
        scol: infer_column_type(vals) for scol, vals in source_samples.items()
    }
    norm_s = {c: normalize(c) for c in source_cols}
    used: set[str] = set()
    mappings: list[ColumnMapping] = []

    for tcol in template_cols:
        norm_t = normalize(tcol)
        best: tuple[float, str] | None = None
        for scol in source_cols:
            if scol in used:
                continue
            if norm_s[scol] == norm_t:  # exact (accent-folded) match wins
                best = (100.0, scol)
                break
            score = score_pair(
                tcol, scol,
                template_types.get(tcol),
                source_types.get(scol),
                synonyms,
            )
            if best is None or score > best[0]:
                best = (score, scol)
        if best is None or best[0] < threshold:
            mappings.append(ColumnMapping(template_col=tcol, source_col=None))
        else:
            score, scol = best
            used.add(scol)
            via_synonym = bool(
                synonyms is not None
                and normalize(scol) in synonyms.aliases(tcol)
            )
            if via_synonym:
                source = MatchSource.SYNONYM
            elif score >= 99.9:
                source = MatchSource.EXACT
            else:
                source = MatchSource.FUZZY
            mappings.append(
                ColumnMapping(
                    template_col=tcol,
                    source_col=scol,
                    match_source=source,
                    confidence=round(score, 1),
                )
            )
    return mappings


def unmapped_source_cols(
    source_cols: list[str], mappings: list[ColumnMapping]
) -> list[str]:
    mapped = {m.source_col for m in mappings if m.source_col}
    return [c for c in source_cols if c not in mapped]
