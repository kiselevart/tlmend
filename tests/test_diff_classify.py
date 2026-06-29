"""Tests for diff/classify — must be fully deterministic, no LLM."""

import pytest

from tlmend.models import HunkClass
from tlmend.pipeline.diff_classify import _classify, apply_resolutions, diff_chapter
from tests.conftest import make_chapter


# --- classification ---

def test_mechanical_whitespace_only() -> None:
    assert _classify("Hello world", "Hello  world") == HunkClass.MECHANICAL


def test_mechanical_punctuation_only() -> None:
    assert _classify("Hello world", "Hello, world.") == HunkClass.MECHANICAL


def test_substantive_word_change() -> None:
    assert _classify("The hero walked quickly.", "The hero sprinted.") == HunkClass.SUBSTANTIVE


def test_substantive_sentence_removed() -> None:
    original = "She spoke. He listened carefully."
    proposed = "She spoke."
    assert _classify(original, proposed) == HunkClass.SUBSTANTIVE


def test_mass_shrink_is_substantive() -> None:
    original = "A" * 200
    proposed = "A" * 10  # >15% shrink
    assert _classify(original, proposed) == HunkClass.SUBSTANTIVE


def test_small_shrink_can_be_mechanical() -> None:
    # removing trailing punctuation is mechanical and < threshold
    assert _classify("Hello world!", "Hello world") == HunkClass.MECHANICAL


# --- diff_chapter ---

def test_diff_no_changes() -> None:
    ch = make_chapter(["same text", "also same"])
    hunks = diff_chapter(ch, ["same text", "also same"])
    assert hunks == []


def test_diff_detects_change() -> None:
    ch = make_chapter(["original sentence here."])
    hunks = diff_chapter(ch, ["original sentence here"])
    assert len(hunks) == 1
    assert hunks[0].index == 0


def test_diff_paragraph_count_mismatch() -> None:
    ch = make_chapter(["para one", "para two"])
    with pytest.raises(ValueError, match="Paragraph count mismatch"):
        diff_chapter(ch, ["para one"])  # missing a paragraph


def test_diff_classifies_correctly() -> None:
    ch = make_chapter(["He went fast.", "She is brave."])
    edited = ["He went fast", "She is extremely brave."]
    hunks = diff_chapter(ch, edited)
    assert len(hunks) == 2
    assert hunks[0].classification == HunkClass.MECHANICAL  # only period removed
    assert hunks[1].classification == HunkClass.SUBSTANTIVE  # word added


# --- apply_resolutions ---

def test_apply_resolutions_partial() -> None:
    ch = make_chapter(["para zero", "para one", "para two"])
    finals = {1: "para ONE (corrected)"}
    result = apply_resolutions(ch, finals)
    assert result.paragraphs[0].text == "para zero"
    assert result.paragraphs[1].text == "para ONE (corrected)"
    assert result.paragraphs[2].text == "para two"


def test_apply_resolutions_preserves_count() -> None:
    ch = make_chapter(["a", "b", "c"])
    result = apply_resolutions(ch, {})
    assert len(result.paragraphs) == 3
