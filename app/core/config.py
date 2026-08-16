"""App settings persistence (config/settings.json, gitignored)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .ai_matcher import AIConfig, DEFAULT_BASE_URL, default_base_url, default_cache_path
from .cleaner import CleanRules

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

_PATH_FIELDS = ("last_template", "last_output_dir", "templates_dir")

# Any of these spellings means "the local AI endpoint" and gets rewritten to the
# platform-correct one on load (Windows 127.0.0.1, WSL gateway IP).
_LOCAL_AI_URLS = (
    "http://127.0.0.1:20128/v1",
    "http://localhost:20128/v1",
    "http://127.0.0.1:20128",
    "http://localhost:20128",
    DEFAULT_BASE_URL,
    DEFAULT_BASE_URL.rstrip("/v1"),
)


def _normalize_ai_base_url(url: str) -> str:
    norm = url.rstrip("/")
    if norm in _LOCAL_AI_URLS:
        return default_base_url()
    return url


def _to_wsl_posix(path: str) -> str:
    """Normalize any /mnt/x/..., \\mnt\\x\\... form to /mnt/x/... (POSIX)."""
    norm = path.replace("\\", "/")
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", norm)
    if m:
        return f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    return path


def _wsl_to_windows(path: str) -> str:
    """Convert /mnt/d/foo (any separator) to D:\\foo."""
    posix = _to_wsl_posix(path)
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", posix)
    if not m:
        return path
    return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")


def _windows_to_wsl(path: str) -> str:
    """Convert D:\\foo (or D:/foo, or any \\mnt\\d\\ form) to /mnt/d/foo."""
    posix = _to_wsl_posix(path)
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", posix)
    if m:
        return f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    norm = path.replace("\\", "/")
    m2 = re.match(r"^([a-zA-Z]):/(.*)$", norm)
    if m2:
        return f"/mnt/{m2.group(1).lower()}/{m2.group(2)}"
    return path


def _platform_path(path: str) -> str:
    """Translate a stored path so it is valid on the current platform."""
    if not path:
        return path
    return _wsl_to_windows(path) if os.name == "nt" else _windows_to_wsl(path)


@dataclass
class AppSettings:
    ai: AIConfig = field(default_factory=AIConfig)
    clean: CleanRules = field(default_factory=CleanRules)
    fuzzy_threshold: float = 60.0
    default_sheet: str | None = None
    default_skip_rows: int = 0
    last_template: str = ""
    last_output_dir: str = ""
    templates_dir: str = str(ROOT / "templates")

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "AppSettings":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        settings = cls()
        if "ai" in data:
            settings.ai = AIConfig(**data["ai"])
        # Any "local endpoint" spelling (localhost / 127.0.0.1 / WSL gateway)
        # must become the platform-correct one for this run.
        settings.ai.base_url = _normalize_ai_base_url(settings.ai.base_url)
        if "clean" in data:
            settings.clean = CleanRules(**data["clean"])
        for k in _PATH_FIELDS:
            if k in data:
                setattr(settings, k, _platform_path(data[k]))
        return settings

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ai": asdict(self.ai),
            "clean": asdict(self.clean),
            "fuzzy_threshold": self.fuzzy_threshold,
            "default_sheet": self.default_sheet,
            "default_skip_rows": self.default_skip_rows,
            "last_template": self.last_template,
            "last_output_dir": self.last_output_dir,
            "templates_dir": self.templates_dir,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def cache_path(self) -> Path:
        return default_cache_path()


def ai_cache_default_path() -> Path:
    return default_cache_path()
