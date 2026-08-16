import pandas as pd
import pytest

from app.core.ai_matcher import AIMatcher, AIConfig
from app.core.config import AppSettings
from app.core.models import Template, TemplateColumn
from app.core.processor import build_mappings


class StubAI:
    def __init__(self):
        self.asked_template_cols = None
        self.asked_source_cols = None

    def available(self):
        return True

    def suggest(self, template_cols, source_cols, template_types=None, source_types=None):
        self.asked_template_cols = list(template_cols)
        self.asked_source_cols = list(source_cols)
        return {"Ngày sinh": "NS"}


def _template():
    return Template(
        path="", sheet_name="",
        columns=[
            TemplateColumn("Mã NV", order=0),
            TemplateColumn("Tên", order=1),
            TemplateColumn("Ngày sinh", order=2),
            TemplateColumn("Lương", order=3),
        ],
    )


def test_ai_only_gets_unmatched_columns():
    settings = AppSettings()
    stub = StubAI()
    mappings = build_mappings(
        _template(),
        ["Ma_NV", "Ten", "NS", "Luong", "Phu chu"],
        settings,
        cache=stub,  # type: ignore[arg-type]
    )
    # Exactly matched columns must NOT reach the AI (0-token layers).
    assert stub.asked_template_cols == ["Ngày sinh"]
    assert "Ma_NV" not in stub.asked_source_cols
    assert "Ten" not in stub.asked_source_cols
    assert "Luong" not in stub.asked_source_cols
    by_tpl = {m.template_col: m for m in mappings}
    assert by_tpl["Ngày sinh"].source_col == "NS"
    assert by_tpl["Ngày sinh"].match_source.value == "ai"


def test_ai_unavailable_falls_back_to_fuzzy():
    settings = AppSettings()
    settings.ai.enabled = False
    mappings = build_mappings(
        _template(),
        ["Ma_NV", "Ten", "NS", "Luong", "Phu chu"],
        settings,
    )
    by_tpl = {m.template_col: m for m in mappings}
    assert by_tpl["Ngày sinh"].source_col is None
