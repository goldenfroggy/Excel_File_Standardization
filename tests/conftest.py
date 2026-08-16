import pandas as pd
import pytest

from app.core.template import save_meta
from app.core.models import Template, TemplateColumn


@pytest.fixture
def tmp_project(tmp_path):
    return tmp_path


@pytest.fixture
def template_path(tmp_path):
    path = tmp_path / "mau.xlsx"
    pd.DataFrame(columns=["Mã NV", "Tên", "Ngày sinh", "Lương"]).to_excel(path, index=False)
    tpl = Template(
        path=path,
        sheet_name="",
        columns=[
            TemplateColumn("Mã NV", required=True, order=0),
            TemplateColumn("Tên", required=True, order=1),
            TemplateColumn("Ngày sinh", data_type="date", order=2),
            TemplateColumn("Lương", data_type="number", default_value=0, order=3),
        ],
    )
    save_meta(tpl)
    return path


@pytest.fixture
def csv_sources(tmp_path):
    files = []
    rows = [
        ["Ma_NV", "Ten", "Ngay sinh", "Luong", "Ghi chu"],
        ["A1", "  An  ", "2000-02-01", "1,000,000", "x"],
        ["A2", "Binh", "15/03/1999", "2.500.000", "y"],
    ]
    for i in range(2):
        p = tmp_path / f"source_{i}.csv"
        pd.DataFrame(rows[1:], columns=rows[0]).to_csv(p, index=False)
        files.append(p)
    return files


@pytest.fixture
def xlsx_source(tmp_path):
    path = tmp_path / "source.xlsx"
    pd.DataFrame(
        columns=["Ma_NV", "Ten", "Ngay sinh", "Luong", "Ghi chu"],
        data=[["A1", "An", "2000-02-01", "1,000,000", "x"]],
    ).to_excel(path, index=False)
    return path
