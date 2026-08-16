from app.core.config import (
    _normalize_ai_base_url,
    _platform_path,
    _windows_to_wsl,
    _wsl_to_windows,
)
from app.core.ai_matcher import default_base_url


def test_wsl_to_windows():
    assert _wsl_to_windows("/mnt/d/project/templates") == "D:\\project\\templates"
    assert _wsl_to_windows("\\mnt\\d\\foo\\bar") == "D:\\foo\\bar"
    assert _wsl_to_windows("C:\\already\\windows") == "C:\\already\\windows"
    assert _wsl_to_windows("") == ""


def test_windows_to_wsl():
    assert _windows_to_wsl("D:\\project\\templates") == "/mnt/d/project/templates"
    assert _windows_to_wsl("D:/project/templates") == "/mnt/d/project/templates"
    assert _windows_to_wsl("/mnt/d/already/wsl") == "/mnt/d/already/wsl"
    assert _windows_to_wsl("\\mnt\\d\\mangled") == "/mnt/d/mangled"
    assert _windows_to_wsl("") == ""


def test_platform_path_roundtrip():
    assert _windows_to_wsl(_wsl_to_windows("/mnt/d/a/b")) == "/mnt/d/a/b"


def test_normalize_ai_base_url_local_variants():
    expected = default_base_url()
    for url in (
        "http://127.0.0.1:20128/v1",
        "http://localhost:20128/v1",
        "http://127.0.0.1:20128",
        "http://localhost:20128",
        "http://172.21.224.1:20128/v1",
        "http://172.21.224.1:20128",
    ):
        assert _normalize_ai_base_url(url) == expected, url
    assert _normalize_ai_base_url("http://example.com:8080/v1") == "http://example.com:8080/v1"
    assert _normalize_ai_base_url("") == ""
