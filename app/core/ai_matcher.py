"""AI-assisted column matching with maximum token economy.

Only unmatched columns reach the AI. Prompts are compact single-liners,
responses are strict JSON with a tiny max_tokens budget, and every result is
cached (in-memory + on-disk) so repeated runs cost 0 tokens.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .matcher import normalize

DEFAULT_BASE_URL = "http://172.21.224.1:20128/v1"
DEFAULT_MODEL = "auto/fast"
CACHE_VERSION = 2


def default_base_url() -> str:
    """On Windows the local AI endpoint is 127.0.0.1; from WSL it is the host gateway."""
    if os.name == "nt":
        return "http://127.0.0.1:20128/v1"
    return DEFAULT_BASE_URL


@dataclass
class AIConfig:
    enabled: bool = True
    api_key: str = ""
    base_url: str = field(default_factory=default_base_url)
    model: str = DEFAULT_MODEL
    timeout: float = 60.0
    temperature: float = 0.0
    max_tokens: int = 300
    aggressive: bool = False


class AICache:
    """Persistent cache of AI mapping results keyed by content hash."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._mem: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") == CACHE_VERSION:
                self._mem = data.get("entries", {})
        except (OSError, json.JSONDecodeError):
            self._mem = {}

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": CACHE_VERSION, "entries": self._mem}
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def get(self, key: str) -> dict[str, str] | None:
        return self._mem.get(key)

    def put(self, key: str, mapping: dict[str, str]) -> None:
        self._mem[key] = mapping


def cache_key(
    model: str,
    template_cols: list[str],
    source_cols: list[str],
    template_types: dict[str, str] | None = None,
    source_types: dict[str, str] | None = None,
) -> str:
    tt = sorted(f"{normalize(c)}={(template_types or {}).get(c, '')}" for c in template_cols)
    st = sorted(f"{normalize(c)}={(source_types or {}).get(c, '')}" for c in source_cols)
    payload = "|".join([model] + tt + st)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tagged(cols: list[str], types: dict[str, str] | None) -> str:
    """Compact one-per-line column list, with type hint when known."""
    if not types:
        return "\n".join(cols)
    return "\n".join(
        f"{c} [{types.get(c, 'text')}]" for c in cols
    )


class AIMatcher:
    """Thin OpenAI-compatible client optimized for cheap mapping requests."""

    def __init__(self, config: AIConfig, cache: AICache | None = None) -> None:
        self.config = config
        self.cache = cache or AICache(default_cache_path())

    def available(self) -> bool:
        return self.config.enabled and bool(self.config.api_key)

    def suggest(
        self,
        template_cols: list[str],
        source_cols: list[str],
        template_types: dict[str, str] | None = None,
        source_types: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        """Return {template_col: source_col} for matchable columns, or None on failure.

        Uses cache first, builds a compact prompt, and falls back to None so the
        caller can rely on fuzzy matching instead.
        """
        if not self.available() or not template_cols or not source_cols:
            return None

        key = cache_key(
            self.config.model, template_cols, source_cols, template_types, source_types
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        mapping = self._call_api(
            template_cols, source_cols, template_types, source_types
        )
        if mapping is None:
            # Some cheap models occasionally answer in prose instead of JSON;
            # one retry meaningfully improves the success rate.
            mapping = self._call_api(
                template_cols, source_cols, template_types, source_types
            )
        if mapping is None:
            return None
        self.cache.put(key, mapping)
        self.cache.save()
        return mapping

    def _call_api(
        self,
        template_cols: list[str],
        source_cols: list[str],
        template_types: dict[str, str] | None = None,
        source_types: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        from openai import OpenAI  # deferred import keeps GUI startup fast

        try:
            client = OpenAI(
                api_key=self.config.api_key, base_url=self.config.base_url,
                timeout=self.config.timeout, max_retries=0,
            )
            system = (
                "Bạn khớp tên cột giữa danh sách 'Cột mẫu' và 'Cột nguồn' dựa trên ý nghĩa. "
                "Phản hồi CHỈ LÀ MỘT đối tượng JSON dạng "
                '{"ten_col_mau":"ten_col_nguon"}'
                " cho các cột khớp được. Tuyệt đối không giải thích, không tiêu đề, "
                "không xuống dòng thừa, không dấu backtick."
            )
            user = (
                "Cột mẫu:\n"
                + _tagged(template_cols, template_types)
                + "\nCột nguồn:\n"
                + _tagged(source_cols, source_types)
                + "\nJSON:"
            )
            resp = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            content = resp.choices[0].message.content or ""
            return self._parse(content, template_cols, source_cols)
        except Exception:
            return None

    @staticmethod
    def _parse(
        content: str, template_cols: list[str], source_cols: list[str]
    ) -> dict[str, str] | None:
        t_set = set(template_cols)
        s_set = set(source_cols)
        result: dict[str, str] = {}

        content = content.strip()
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in t_set and v in s_set and k not in result:
                        result[k] = str(v)
                return result

        # Fallback: models sometimes reply with "X -> Y" lines or explain in prose
        # like: 1. STT [text] -> ... Source has "ID [number]". This is a match.
        for line in content.splitlines():
            line = line.strip().lstrip("-0123456789. ").strip()
            for sep in (" -> ", " => ", ": "):
                if sep not in line:
                    continue
                k_part, v_part = line.split(sep, 1)
                k = re.sub(r"\s*\[[^\]]*\]\s*$", "", k_part).strip().strip('"')
                v = re.sub(r"\s*\[[^\]]*\]\s*$", "", v_part).strip().strip('",')
                if k in t_set and v in s_set and k not in result:
                    result[k] = v
                elif k in t_set:
                    quoted = re.search(r'"([^"]+)"', v_part)
                    if quoted:
                        cand = re.sub(
                            r"\s*\[[^\]]*\]\s*$", "", quoted.group(1)
                        ).strip()
                        if cand in s_set and k not in result:
                            result[k] = cand
                break
        return result or None


def default_cache_path() -> Path:
    root = Path(__file__).resolve().parents[2] / "config"
    return root / "ai_cache.json"
