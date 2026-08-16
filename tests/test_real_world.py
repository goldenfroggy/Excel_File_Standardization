import shutil
import tempfile
from pathlib import Path

import pandas as pd

from app.core.config import AppSettings
from app.core.matcher import match_columns
from app.core.models import Template, TemplateColumn
from app.core.processor import build_mappings
from app.core.reader import _read_head, detect_header_row, pick_best_sheet, read_frame
from app.core.synonyms import SynonymStore
from app.core.type_inference import infer_column_type


def _messy_workbook(tmp: Path) -> Path:
    rows = [
        ["BÁO CÁO NHÂN SỰ THÁNG 5/2025", None, None, None, None],
        ["PHÒNG TÀI CHÍNH", None, None, None, None],
        [None, None, None, None, None],
        ["Mã nhân viên", "Họ và tên", "Ngày sinh", "Lương", "SĐT"],
        ["NV001", "Nguyễn An", "2000-02-01", "1.500.000", "0912345678"],
        ["NV002", "Trần Bình", "15/03/1999", "2.000.000", "0987654321"],
    ]
    path = tmp / "messy.xlsx"
    with pd.ExcelWriter(path) as w:
        pd.DataFrame(rows).to_excel(w, sheet_name="Data", index=False, header=False)
        pd.DataFrame([["garbage"]]).to_excel(
            w, sheet_name="Hidden", index=False, header=False
        )
    return path


def test_detect_header_row_with_banner(tmp_path):
    path = _messy_workbook(tmp_path)
    head = _read_head(path, None)
    assert detect_header_row(head) == 3


def test_pick_best_sheet_skips_junk_sheet(tmp_path):
    path = _messy_workbook(tmp_path)
    assert pick_best_sheet(path) == "Data"


def test_read_frame_uses_detected_header(tmp_path):
    path = _messy_workbook(tmp_path)
    df = read_frame(path, sheet_name="Data")
    assert list(df.columns) == ["Mã nhân viên", "Họ và tên", "Ngày sinh", "Lương", "SĐT"]
    assert len(df) == 2


def test_type_inference():
    assert infer_column_type(["1.000.000", "2,5", "3"]) == "number"
    assert infer_column_type(["2000-02-01", "15/03/1999", "01/01/2020"]) == "date"
    assert infer_column_type(["a@b.com", "c@d.vn"]) == "email"
    assert infer_column_type(["0912345678", "0987654321"]) == "phone"
    assert infer_column_type(["NV001", "NV002", "AB-12"]) == "code"
    assert infer_column_type(["Nguyễn An", "Trần Bình"]) == "text"


def _tpl(*pairs):
    return Template(
        path="", sheet_name="",
        columns=[TemplateColumn(name, data_type=typ, order=i)
                 for i, (name, typ) in enumerate(pairs)],
    )


def test_token_overlap_maps_longer_header():
    tpl = _tpl(("Ngày tháng năm sinh", "date"), ("Họ và tên", "text"))
    src = ["Ngay sinh", "Ho ten"]
    mappings = match_columns(
        tpl.column_names, src, threshold=60.0,
        template_types={"Ngày tháng năm sinh": "date", "Họ và tên": "text"},
        source_samples={"Ngay sinh": ["2000-02-01"], "Ho ten": ["Nguyễn An"]},
    )
    by = {m.template_col: m for m in mappings}
    assert by["Ngày tháng năm sinh"].source_col == "Ngay sinh"
    assert by["Họ và tên"].source_col == "Ho ten"


def test_synonym_learning_closes_abbreviation_gap(tmp_path):
    tpl = _tpl(("Mã NV", "code"), ("Ngày sinh", "date"))
    src = ["MSNV", "DOB"]
    samples = {"MSNV": ["NV001"], "DOB": ["2000-02-01"]}
    syn = SynonymStore(tmp_path / "synonyms.json")
    settings = AppSettings()
    settings.ai.enabled = False

    first = build_mappings(tpl, src, settings, source_samples=samples, synonyms=syn)
    assert all(m.source_col is None for m in first)

    syn.add("Mã NV", "MSNV")
    syn.add("Ngày sinh", "DOB")
    second = build_mappings(tpl, src, settings, source_samples=samples, synonyms=syn)
    by = {m.template_col: m for m in second}
    assert by["Mã NV"].source_col == "MSNV"
    assert by["Mã NV"].match_source.value == "synonym"
    assert by["Ngày sinh"].source_col == "DOB"


def test_type_conflict_does_not_match_wrong_column():
    tpl = _tpl(("Ngày sinh", "date"))
    src = ["Ghi chu"]
    mappings = match_columns(
        tpl.column_names, src, threshold=60.0,
        template_types={"Ngày sinh": "date"},
        source_samples={"Ghi chu": ["ghi chú gì đó dài dòng văn bản"]},
    )
    assert mappings[0].source_col is None
