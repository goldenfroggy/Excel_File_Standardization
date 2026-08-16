from datetime import datetime

import pandas as pd

from app.core.cleaner import CleanRules, parse_date, parse_number
from app.core.models import (
    FileReport,
    IssueSeverity,
    Template,
    TemplateColumn,
)
from app.core.cleaner import apply_rules


def test_parse_date_strings():
    assert parse_date("01/02/2000") == datetime(2000, 2, 1)
    assert parse_date("2000-02-01") == datetime(2000, 2, 1)
    assert parse_date("15/03/1999") == datetime(1999, 3, 15)
    assert parse_date("01/02/2000").strftime("%d/%m/%Y") == "01/02/2000"


def test_parse_date_invalid():
    assert parse_date("không phải ngày") is None
    assert parse_date("") is None
    assert parse_date(None) is None


def test_parse_number_currency():
    assert parse_number("1,000,000") == 1000000.0
    assert parse_number("2.500.000") == 2500000.0
    assert parse_number("500,000 ₫") == 500000.0
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("(500)") == -500.0


def test_parse_number_invalid():
    assert parse_number("abc") is None
    assert parse_number("") is None


def test_apply_rules_date_number_defaults():
    template = Template(
        path="",
        sheet_name="",
        columns=[
            TemplateColumn("NS", data_type="date", order=0),
            TemplateColumn("Luong", data_type="number", order=1),
            TemplateColumn("Ten", data_type="text", order=2),
            TemplateColumn("Note", default_value="NA", order=3),
        ],
    )
    df = pd.DataFrame(
        {"NS": ["01/02/2000"], "Luong": ["1,000,000"], "Ten": ["  An  "], "Note": [None]}
    )
    mappings = [
        type("M", (), {"source_col": "NS", "template_col": "NS"})(),
        type("M", (), {"source_col": "Luong", "template_col": "Luong"})(),
        type("M", (), {"source_col": "Ten", "template_col": "Ten"})(),
        type("M", (), {"source_col": "Note", "template_col": "Note"})(),
    ]
    report = FileReport(source_path="", output_path=None, status="ok")
    apply_rules(df, template, mappings, CleanRules.defaults(), report)

    assert df.at[0, "NS"] == "01/02/2000"
    assert df.at[0, "Luong"] == 1000000.0
    assert df.at[0, "Ten"] == "An"
    assert df.at[0, "Note"] == "NA"
    assert report.warning_count == 1


def test_apply_rules_bad_format_reports_error():
    template = Template(
        path="", sheet_name="",
        columns=[TemplateColumn("NS", data_type="date", order=0)],
    )
    df = pd.DataFrame({"NS": ["not-a-date"]})
    mappings = [type("M", (), {"source_col": "NS", "template_col": "NS"})()]
    report = FileReport(source_path="", output_path=None, status="ok")
    apply_rules(df, template, mappings, CleanRules.defaults(), report)
    assert report.error_count == 1
    assert report.issues[0].severity == IssueSeverity.ERROR
