"""Domain models for the Excel standardization app."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MatchSource(str, Enum):
    """How a template column was matched to a source column."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    SYNONYM = "synonym"
    AI = "ai"
    MANUAL = "manual"
    UNMAPPED = "unmapped"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class IssueType(str, Enum):
    MISSING_VALUE = "missing_value"
    BAD_FORMAT = "bad_format"
    EXTRA_COLUMN = "extra_column"
    UNMAPPED_COLUMN = "unmapped_column"
    DUPLICATE_HEADER = "duplicate_header"


@dataclass
class ColumnMapping:
    """A single template-column -> source-column mapping."""

    template_col: str
    source_col: str | None
    match_source: MatchSource = MatchSource.UNMAPPED
    confidence: float = 0.0


@dataclass
class TemplateColumn:
    """Definition of a column in the template."""

    name: str
    required: bool = False
    default_value: Any = None
    data_type: str | None = None  # e.g. "date", "number", "text"
    order: int = 0


@dataclass
class Template:
    """Parsed template file."""

    path: Path
    sheet_name: str
    columns: list[TemplateColumn]

    @property
    def required_columns(self) -> list[TemplateColumn]:
        return [c for c in self.columns if c.required]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


@dataclass
class Issue:
    """A problem detected on a row/column during processing."""

    row: int
    column: str
    severity: IssueSeverity
    type: IssueType
    message: str
    value: Any = None


@dataclass
class FileReport:
    """Report for a single processed file."""

    source_path: Path
    output_path: Path | None
    status: str  # "ok", "partial", "failed"
    row_count: int = 0
    mapped_columns: int = 0
    unmapped_columns: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    error_message: str | None = None

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)


@dataclass
class BatchReport:
    """Aggregate report for a batch run."""

    reports: list[FileReport] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.reports if r.status == "ok")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.reports if r.status == "failed")
