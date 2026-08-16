from app.core.matcher import match_columns, normalize, unmapped_source_cols


def test_normalize_folds_accents_and_case():
    assert normalize("Mã NV") == normalize("ma nv")
    assert normalize("Lương") == "luong"
    assert normalize("  Ho  Ten  ") == "ho ten"


def test_exact_match():
    mappings = match_columns(["Mã NV"], ["Ma_NV"])
    assert mappings[0].source_col == "Ma_NV"
    assert mappings[0].confidence == 100.0
    assert mappings[0].match_source.value == "exact"


def test_fuzzy_match_below_threshold_unmapped():
    mappings = match_columns(["Ngày sinh"], ["NS"])
    assert mappings[0].source_col is None


def test_fuzzy_match_above_threshold():
    mappings = match_columns(["Họ tên"], ["Ho ten"], threshold=70.0)
    assert mappings[0].source_col == "Ho ten"


def test_source_column_used_once():
    mappings = match_columns(["Họ và tên", "Tên đầy đủ"], ["Ho ten"], threshold=50.0)
    mapped = {m.source_col for m in mappings if m.source_col}
    assert len(mapped) == 1
    assert len([m for m in mappings if m.source_col]) == 1


def test_unmapped_source_cols():
    mappings = match_columns(["Mã NV"], ["Ma_NV", "Ghi chu"])
    assert unmapped_source_cols(["Ma_NV", "Ghi chu"], mappings) == ["Ghi chu"]
