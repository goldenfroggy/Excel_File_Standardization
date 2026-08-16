import pandas as pd

from app.core.config import AppSettings
from app.core.processor import process_batch, process_file
from app.core.template import load_template


def test_process_xlsx_to_xlsx(template_path, xlsx_source, tmp_path):
    tpl = load_template(template_path)
    report = process_file(xlsx_source, tpl, AppSettings(), tmp_path)
    assert report.status == "ok"
    assert report.output_path.exists()
    out = pd.read_excel(report.output_path)
    assert list(out.columns) == ["Mã NV", "Tên", "Ngày sinh", "Lương"]
    assert out.at[0, "Mã NV"] == "A1"
    assert out.at[0, "Lương"] == 1000000.0
    assert out.at[0, "Ngày sinh"] == "01/02/2000"


def test_process_csv_reorders_and_defaults(template_path, csv_sources, tmp_path):
    tpl = load_template(template_path)
    report = process_file(csv_sources[0], tpl, AppSettings(), tmp_path)
    out = pd.read_excel(report.output_path)
    assert list(out.columns) == ["Mã NV", "Tên", "Ngày sinh", "Lương"]
    assert out["Mã NV"].tolist() == ["A1", "A2"]
    # default_value=0 filled for missing Lương? Lương present here
    assert out["Lương"].tolist() == [1000000.0, 2500000.0]
    assert out["Tên"].tolist() == ["An", "Binh"]


def test_unmapped_columns_flagged(template_path, tmp_path):
    src = tmp_path / "no_match.csv"
    pd.DataFrame(columns=["xxx", "yyy"], data=[["a", "b"]]).to_csv(src, index=False)
    tpl = load_template(template_path)
    report = process_file(src, tpl, AppSettings(), tmp_path)
    assert report.error_count > 0
    assert report.status == "partial"


def test_batch_processes_all_files(template_path, csv_sources, tmp_path):
    tpl = load_template(template_path)
    settings = AppSettings()
    batch = process_batch(csv_sources, tpl, settings, tmp_path, max_workers=2)
    assert batch.ok_count == 2
    assert all(r.output_path.exists() for r in batch.reports)
    for r in batch.reports:
        assert list(pd.read_excel(r.output_path).columns) == [
            "Mã NV", "Tên", "Ngày sinh", "Lương"
        ]
