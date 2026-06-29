"""Tests for validation gates."""

from tlmend.models import Chapter
from tlmend.pipeline.validate import validate
from tests.conftest import make_chapter


def _resolved(paragraphs: list[str]) -> Chapter:
    return make_chapter(paragraphs, chapter_id="r1", title="Resolved")


def test_valid_chapter_passes() -> None:
    original = make_chapter(["The Reverend Insanity sat quietly.", "He pondered."])
    resolved = _resolved(["The Reverend Insanity sat quietly.", "He pondered."])
    result = validate(original, resolved, glossary_terms=["Reverend Insanity"])
    assert result.ok
    assert result.errors == []


def test_paragraph_count_mismatch_fails() -> None:
    original = make_chapter(["para one", "para two"])
    resolved = _resolved(["para one"])
    result = validate(original, resolved, glossary_terms=[])
    assert not result.ok
    assert any("count" in e for e in result.errors)


def test_empty_paragraph_fails() -> None:
    original = make_chapter(["para one", "para two"])
    resolved = _resolved(["para one", ""])
    result = validate(original, resolved, glossary_terms=[])
    assert not result.ok
    assert any("empty" in e for e in result.errors)


def test_missing_glossary_term_fails() -> None:
    original = make_chapter(["Reverend Insanity is powerful."])
    resolved = _resolved(["The protagonist is powerful."])
    result = validate(original, resolved, glossary_terms=["Reverend Insanity"])
    assert not result.ok
    assert any("Reverend Insanity" in e for e in result.errors)


def test_multiple_glossary_terms_one_missing() -> None:
    original = make_chapter(["Fang Yuan and Gu Yue."])
    resolved = _resolved(["Fang Yuan spoke."])  # Gu Yue removed
    result = validate(original, resolved, glossary_terms=["Fang Yuan", "Gu Yue"])
    assert not result.ok
    errors_text = " ".join(result.errors)
    assert "Gu Yue" in errors_text
    assert "Fang Yuan" not in errors_text


def test_glossary_case_insensitive() -> None:
    original = make_chapter(["REVEREND INSANITY spoke."])
    resolved = _resolved(["reverend insanity spoke."])
    result = validate(original, resolved, glossary_terms=["Reverend Insanity"])
    assert result.ok


def test_glossary_term_not_in_original_is_ignored() -> None:
    # "Fixed Immortal Travel" doesn't appear in this chapter — should not fail
    original = make_chapter(["Fang Yuan sat quietly."])
    resolved = _resolved(["Fang Yuan sat quietly."])
    result = validate(original, resolved, glossary_terms=["Fang Yuan", "Fixed Immortal Travel"])
    assert result.ok
