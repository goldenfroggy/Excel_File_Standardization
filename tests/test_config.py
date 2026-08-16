from app.core.config import _platform_path, _windows_to_wsl, _wsl_to_windows


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
