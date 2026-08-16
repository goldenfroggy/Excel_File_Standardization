"""Tests against real user-provided sample files (gitignored).

These are skipped when tests/samples is empty so the suite stays green in CI.
"""

from pathlib import Path

import pandas as pd
import pytest

from app.core.config import AppSettings
from app.core.processor import process_batch
from app.core.synonyms import SynonymStore
from app.core.template import load_template

SAMPLES = Path(__file__).parent / "samples"
MAU = SAMPLES / "mau"
NGUON = SAMPLES / "nguon"


def _has_samples() -> bool:
    return any(MAU.glob("*.xlsx")) and any(NGUON.glob("*.xlsx"))


pytestmark = pytest.mark.skipif(
    not _has_samples(), reason="user sample files not present"
)


@pytest.fixture(scope="module")
def template():
    m = sorted(MAU.glob("*.xlsx"))[0]
    return load_template(m)


def test_all_real_files_standardized(tmp_path, template):
    settings = AppSettings()
    settings.ai.enabled = False
    syn = SynonymStore(tmp_path / "synonyms.json")
    # teach once for the two "renamed" structures (nguon2 Vietnamese-abbrev,
    # nguon3 English). nguon1 (transposed) maps automatically.
    for t, s in [("STT", "S"), ("Họ và tên", "HoTen"), ("Số tiền", "Tien"),
                 ("Địa chỉ", "DiaChi"), ("Ghi chú", "GC"),
                 ("STT", "ID"), ("Họ và tên", "Name"), ("Số tiền", "Money"),
                 ("Địa chỉ", "Address"), ("Ghi chú", "Note")]:
        syn.add(t, s)

    files = sorted(NGUON.glob("*.xlsx"))
    out = tmp_path / "out"
    batch = process_batch(files, template, settings, out, synonyms=syn)
    assert batch.ok_count == len(files), [r.error_message for r in batch.reports]
    for r in batch.reports:
        df = pd.read_excel(r.output_path)
        assert list(df.columns) == template.column_names
        assert len(df) >= 3
        assert df.notna().sum().sum() > 0
