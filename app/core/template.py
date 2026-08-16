"""Template loading and metadata handling.

A template is an Excel/CSV file whose first row defines the target column names.
Optional sidecar JSON file (same basename + ".template.json") holds per-column
metadata: required flag, default value, data type.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Template, TemplateColumn
from .reader import read_frame_head

META_SUFFIX = ".template.json"


def load_template(
    path: Path | str,
    sheet_name: str | None = None,
    skip_rows: int = 0,
    encoding: str = "utf-8-sig",
) -> Template:
    """Load a template file and parse its header row into TemplateColumn list."""
    path = Path(path)
    header = read_frame_head(
        path, sheet_name=sheet_name, skip_rows=skip_rows, encoding=encoding
    )
    columns = [_header_to_column(name, i) for i, name in enumerate(header)]
    template = Template(path=path, sheet_name=sheet_name or "", columns=columns)

    meta = load_meta(path)
    if meta is not None:
        template.columns = _apply_meta(columns, meta)
    return template


def _header_to_column(name: str, order: int) -> TemplateColumn:
    return TemplateColumn(name=name or f"COL_{order + 1}", order=order)


def _apply_meta(
    columns: list[TemplateColumn], meta: dict[str, Any]
) -> list[TemplateColumn]:
    settings = meta.get("columns", {})
    for col in columns:
        spec = settings.get(col.name)
        if not spec:
            continue
        col.required = bool(spec.get("required", False))
        col.default_value = spec.get("default")
        col.data_type = spec.get("type")
    return columns


def meta_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + META_SUFFIX)


def load_meta(path: Path) -> dict[str, Any] | None:
    mp = meta_path(path)
    if not mp.exists():
        return None
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_meta(template: Template) -> Path:
    """Persist per-column metadata as a sidecar JSON next to the template."""
    settings = {
        c.name: {
            "required": c.required,
            "default": c.default_value,
            "type": c.data_type,
        }
        for c in template.columns
        if c.required or c.default_value is not None or c.data_type
    }
    payload = {"columns": settings}
    mp = meta_path(template.path)
    mp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return mp
