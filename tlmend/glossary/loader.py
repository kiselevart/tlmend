"""Load and validate the project glossary."""

from __future__ import annotations

import json
from pathlib import Path


def load_glossary(path: Path) -> list[str]:
    """Return a flat list of protected terms from a glossary JSON file.

    The file must be a JSON object of ``{"terms": ["Term1", "Term2", ...]}``.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("terms", [])
    if not isinstance(raw, list):
        raise ValueError(f"glossary 'terms' must be a list, got {type(raw)}")
    return [str(t) for t in raw]


def validate_glossary(terms: list[str], text: str) -> list[str]:
    """Return terms from *terms* that are absent from *text*."""
    return [t for t in terms if t.lower() not in text.lower()]
