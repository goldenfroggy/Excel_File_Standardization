"""Persistent mapping presets keyed by (template, source header signature)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .matcher import normalize
from .models import ColumnMapping, MatchSource

PRESETS_PATH = Path(__file__).resolve().parents[2] / "config" / "presets.json"
VERSION = 1


class PresetStore:
    def __init__(self, path: Path = PRESETS_PATH) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") == VERSION:
                self._data = data.get("entries", {})
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": VERSION, "entries": self._data}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _key(template_path: str, source_cols: list[str]) -> str:
        sig = "|".join(sorted(normalize(c) for c in source_cols))
        return hashlib.sha256(f"{template_path}::{sig}".encode("utf-8")).hexdigest()

    def get(
        self, template_path: str, source_cols: list[str]
    ) -> list[ColumnMapping] | None:
        entry = self._data.get(self._key(template_path, source_cols))
        if not entry:
            return None
        return [
            ColumnMapping(
                template_col=m["template_col"],
                source_col=m["source_col"],
                match_source=MatchSource(m.get("match_source", "manual")),
                confidence=float(m.get("confidence", 100.0)),
            )
            for m in entry
        ]

    def put(
        self,
        template_path: str,
        source_cols: list[str],
        mappings: list[ColumnMapping],
    ) -> None:
        key = self._key(template_path, source_cols)
        self._data[key] = [
            {
                "template_col": m.template_col,
                "source_col": m.source_col,
                "match_source": m.match_source.value,
                "confidence": m.confidence,
            }
            for m in mappings
        ]
        self._save()

    def keys(self) -> list[str]:
        return list(self._data.keys())
