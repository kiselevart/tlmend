"""Tests for canonical data models."""

import pytest

from tlmend.models import Chapter, ChapterStatus, Paragraph


def test_chapter_paragraph_index_validation() -> None:
    with pytest.raises(ValueError, match="index mismatch"):
        Chapter(
            id="c1",
            title="Chapter 1",
            paragraphs=[Paragraph(index=5, text="wrong index")],
        )


def test_chapter_valid() -> None:
    ch = Chapter(
        id="c1",
        title="Chapter 1",
        paragraphs=[Paragraph(index=0, text="hello"), Paragraph(index=1, text="world")],
    )
    assert len(ch.paragraphs) == 2


def test_chapter_status_values() -> None:
    assert ChapterStatus.PENDING == "pending"
    assert ChapterStatus.ASSEMBLED == "assembled"
