"""Batch processing engine: mapping -> cleaning -> output -> report."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import pandas as pd

from .ai_matcher import AIMatcher
from .cleaner import apply_rules
from .config import AppSettings
from .matcher import match_columns, unmapped_source_cols
from .models import (
    BatchReport,
    ColumnMapping,
    FileReport,
    Issue,
    IssueSeverity,
    IssueType,
    MatchSource,
    Template,
)
from .reader import read_frame
from .synonyms import SynonymStore

ProgressCallback = Callable[[FileReport], None]


def _output_path(source: Path, output_dir: Path) -> Path:
    return output_dir / f"{source.stem}_standardized.xlsx"


def _sample_frame_values(df: pd.DataFrame, limit: int = 20) -> dict[str, list]:
    samples: dict[str, list] = {}
    for col in df.columns:
        vals = []
        for v in df[col].tolist():
            if v is None:
                continue
            if isinstance(v, float) and v != v:  # NaN
                continue
            vals.append(v)
        samples[col] = vals[:limit]
    return samples


def _infer_type(values: list) -> str:
    from .type_inference import infer_column_type

    return infer_column_type(values)


def build_mappings(
    template: Template,
    source_cols: list[str],
    settings: AppSettings,
    cache: AIMatcher | None = None,
    source_samples: dict[str, list] | None = None,
    synonyms: SynonymStore | None = None,
) -> list[ColumnMapping]:
    """Combined local matching (name + token + type + synonyms), then AI only
    for the columns still unmatched."""
    template_types = {c.name: (c.data_type or "text") for c in template.columns}
    source_types = {
        scol: _infer_type(vals) for scol, vals in (source_samples or {}).items()
    }
    mappings = match_columns(
        template.column_names,
        source_cols,
        settings.fuzzy_threshold,
        template_types=template_types,
        source_samples=source_samples,
        synonyms=synonyms,
    )

    unmatched = [m.template_col for m in mappings if m.source_col is None]
    ai = cache or AIMatcher(settings.ai)
    if unmatched and ai.available():
        remaining_src = unmapped_source_cols(source_cols, mappings)
        if remaining_src:
            ai_map = ai.suggest(
                unmatched, remaining_src, template_types, source_types
            ) or {}
            by_tpl = {m.template_col: m for m in mappings}
            for tcol, scol in ai_map.items():
                if tcol in by_tpl and by_tpl[tcol].source_col is None:
                    by_tpl[tcol].source_col = scol
                    by_tpl[tcol].match_source = MatchSource.AI
                    by_tpl[tcol].confidence = 90.0

    # "AI mạnh hơn": ask AI to confirm/replace low-confidence fuzzy matches too.
    if settings.ai.aggressive and ai.available():
        by_tpl = {m.template_col: m for m in mappings}
        used = {m.source_col for m in mappings if m.source_col}
        free_srcs = [c for c in source_cols if c not in used]
        low = [
            m.template_col
            for m in mappings
            if m.source_col and m.match_source == MatchSource.FUZZY and m.confidence < 75
        ]
        if low and free_srcs:
            ai_map = ai.suggest(low, free_srcs, template_types, source_types) or {}
            for tcol, scol in ai_map.items():
                m = by_tpl.get(tcol)
                if m and scol in free_srcs and scol not in used:
                    m.source_col = scol
                    m.match_source = MatchSource.AI
                    m.confidence = 90.0
                    used.add(scol)
    return mappings


def process_file(
    source: Path,
    template: Template,
    settings: AppSettings,
    output_dir: Path,
    sheet_name: str | None = None,
    skip_rows: int = 0,
    cache: AIMatcher | None = None,
    mappings_override: list[ColumnMapping] | None = None,
    synonyms: SynonymStore | None = None,
) -> FileReport:
    report = FileReport(source_path=source, output_path=None, status="failed")
    try:
        if sheet_name is None:
            from .reader import pick_best_sheet

            sheet_name = pick_best_sheet(source)
        df = read_frame(source, sheet_name=sheet_name, skip_rows=skip_rows)
        if df.empty:
            raise ValueError("File không có dữ liệu")

        report.row_count = len(df)
        source_cols = list(df.columns)
        if mappings_override is not None:
            present = set(source_cols)
            mappings = [
                m if m.source_col in present else ColumnMapping(
                    template_col=m.template_col, source_col=None
                )
                for m in mappings_override
            ]
        else:
            mappings = build_mappings(
                template,
                source_cols,
                settings,
                cache,
                source_samples=_sample_frame_values(df),
                synonyms=synonyms,
            )

        report.mapped_columns = sum(1 for m in mappings if m.source_col)
        report.unmapped_columns = [
            m.template_col for m in mappings if m.source_col is None
        ]

        extra = unmapped_source_cols(source_cols, mappings)
        for col in extra:
            report.issues.append(
                Issue(0, col, IssueSeverity.WARNING, IssueType.EXTRA_COLUMN,
                      f"Cột không khớp với mẫu, sẽ bị bỏ qua: {col}")
            )
        for col in report.unmapped_columns:
            report.issues.append(
                Issue(0, col, IssueSeverity.ERROR, IssueType.UNMAPPED_COLUMN,
                      f"Không tìm thấy cột nguồn cho cột mẫu: {col}")
            )

        # Clean data on the source frame (source column names exist there),
        # then reorder to follow the template column order.
        stats = apply_rules(df, template, mappings, settings.clean, report)
        out = _reorder(df, template, mappings)

        out_path = _output_path(source, output_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_excel(out_path, index=False, engine="openpyxl")

        report.output_path = out_path
        report.status = "ok" if not report.error_count else "partial"
        report.row_count = len(out)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the report
        report.error_message = str(exc)
        report.status = "failed"
    return report


def _reorder(
    df: pd.DataFrame, template: Template, mappings: list[ColumnMapping]
) -> pd.DataFrame:
    src_to_tpl = {m.source_col: m.template_col for m in mappings if m.source_col}
    default_by_tpl = {c.name: c.default_value for c in template.columns}

    result = pd.DataFrame()
    for col in template.columns:
        if col.name in src_to_tpl.values():
            src_col = next(s for s, t in src_to_tpl.items() if t == col.name)
            result[col.name] = df[src_col].values
        else:
            result[col.name] = pd.Series([None] * len(df), dtype=object)
    result.index = df.index
    return result


def process_batch(
    files: list[Path],
    template: Template,
    settings: AppSettings,
    output_dir: Path,
    sheet_name: str | None = None,
    skip_rows: int = 0,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    max_workers: int | None = None,
    mappings_override: list[ColumnMapping] | None = None,
    synonyms: SynonymStore | None = None,
) -> BatchReport:
    """Process many files concurrently. A shared AI cache cuts tokens to 1 call
    per unique header structure across the whole batch."""
    cache = AIMatcher(settings.ai)
    if synonyms is None:
        synonyms = SynonymStore()
    workers = max_workers or max(1, min(8, (__import__("os").cpu_count() or 2)))
    batch = BatchReport()

    if cancel_event and cancel_event.is_set():
        return batch

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_file, f, template, settings, output_dir, sheet_name,
                skip_rows, cache, mappings_override, synonyms,
            ): f
            for f in files
        }
        for future in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                break
            report = future.result()
            batch.reports.append(report)
            if progress:
                progress(report)
    return batch
