"""Tests for glossary loader."""

import json
import tempfile
from pathlib import Path

import pytest

from tlmend.glossary.loader import load_glossary, validate_glossary


def test_load_glossary_basic() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        json.dump({"terms": ["Reverend Insanity", "Fang Yuan"]}, f)
        path = Path(f.name)
    try:
        terms = load_glossary(path)
        assert terms == ["Reverend Insanity", "Fang Yuan"]
    finally:
        path.unlink()


def test_load_glossary_empty_terms() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        json.dump({"terms": []}, f)
        path = Path(f.name)
    try:
        terms = load_glossary(path)
        assert terms == []
    finally:
        path.unlink()


def test_load_glossary_missing_key() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        json.dump({}, f)
        path = Path(f.name)
    try:
        terms = load_glossary(path)
        assert terms == []
    finally:
        path.unlink()


def test_load_glossary_invalid_type() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        json.dump({"terms": "not a list"}, f)
        path = Path(f.name)
    try:
        with pytest.raises(ValueError, match="must be a list"):
            load_glossary(path)
    finally:
        path.unlink()


def test_validate_glossary_all_present() -> None:
    missing = validate_glossary(["Fang Yuan", "Gu Yue"], "Fang Yuan and Gu Yue met.")
    assert missing == []


def test_validate_glossary_one_missing() -> None:
    missing = validate_glossary(["Fang Yuan", "Gu Yue"], "Fang Yuan spoke.")
    assert missing == ["Gu Yue"]


def test_validate_glossary_case_insensitive() -> None:
    missing = validate_glossary(["Reverend Insanity"], "reverend insanity is here.")
    assert missing == []


def test_validate_glossary_empty_terms() -> None:
    missing = validate_glossary([], "any text at all")
    assert missing == []
