"""Editable synonym dictionary for column-name matching.

Persisted at config/synonyms.json (gitignored). The app learns automatically:
whenever the user manually maps a source column to a template column, the pair
is added here so later runs match without AI or fuzzy guesswork.
"""

from __future__ import annotations

import json
from pathlib import Path

from .matcher import normalize

SYNONYMS_PATH = Path(__file__).resolve().parents[2] / "config" / "synonyms.json"
VERSION = 1


class SynonymStore:
    def __init__(self, path: Path = SYNONYMS_PATH) -> None:
        self.path = path
        self._data: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") == VERSION:
                self._data = {
                    tpl: [normalize(a) for a in aliases]
                    for tpl, aliases in data.get("aliases", {}).items()
                }
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": VERSION, "aliases": self._data}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def aliases(self, template_col: str) -> set[str]:
        """Return normalized aliases known for a template column."""
        return set(self._data.get(template_col, []))

    def add(self, template_col: str, alias: str) -> None:
        """Remember that ``alias`` maps to ``template_col``."""
        norm = normalize(alias)
        if not norm:
            return
        aliases = self._data.setdefault(template_col, [])
        if norm not in aliases:
            aliases.append(norm)
            self._save()

    def add_many(self, template_col: str, aliases: list[str]) -> None:
        changed = False
        existing = self._data.setdefault(template_col, [])
        for a in aliases:
            norm = normalize(a)
            if norm and norm not in existing:
                existing.append(norm)
                changed = True
        if changed:
            self._save()

    def all(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._data.items()}
