from app.core.ai_matcher import AICache, AIMatcher, AIConfig, cache_key


def test_parse_strict_json():
    result = AIMatcher._parse(
        '{"Mã NV": "Ma_NV", "unknown": "zzz", "Lương": "abc"}',
        ["Mã NV", "Lương"],
        ["Ma_NV", "abc"],
    )
    assert result == {"Mã NV": "Ma_NV", "Lương": "abc"}


def test_parse_ignores_wrapped_text():
    result = AIMatcher._parse(
        'Đây là kết quả: {"Tên": "Ten"} done',
        ["Tên"],
        ["Ten"],
    )
    assert result == {"Tên": "Ten"}


def test_parse_invalid_returns_none():
    assert AIMatcher._parse("không phải json", ["a"], ["b"]) is None


def test_parse_arrow_lines_with_type_suffix():
    result = AIMatcher._parse(
        "1. STT [text] -> S\n2. Họ và tên [text] -> HoTen",
        ["STT", "Họ và tên"],
        ["S", "HoTen"],
    )
    assert result == {"STT": "S", "Họ và tên": "HoTen"}


def test_parse_prose_with_quoted_source():
    result = AIMatcher._parse(
        "STT [text] -> Usually serial number. Source has \"ID [number]\". Match.",
        ["STT"],
        ["ID"],
    )
    assert result == {"STT": "ID"}


def test_ai_not_available_without_key():
    matcher = AIMatcher(AIConfig(enabled=True, api_key=""))
    assert matcher.available() is False
    assert matcher.suggest(["a"], ["b"]) is None


def test_cache_key_ignores_order():
    k1 = cache_key("m1", ["a", "b"], ["x", "y"])
    k2 = cache_key("m1", ["b", "a"], ["y", "x"])
    assert k1 == k2


def test_cache_roundtrip(tmp_path):
    cache = AICache(tmp_path / "cache.json")
    cache.put("k", {"a": "x"})
    cache.save()
    cache2 = AICache(tmp_path / "cache.json")
    assert cache2.get("k") == {"a": "x"}
