"""Tests for input/output adapters."""

import tempfile
from pathlib import Path

from tlmend.adapters.input.txt import TxtAdapter, _parse
from tlmend.adapters.output.txt import TxtOutputAdapter
from tests.conftest import make_chapter


# --- txt input adapter ---

_SIMPLE_TEXT = """\
Chapter 1

The hero walked into the forest.

She carried a sword.

Chapter 2

The villain laughed.
"""


def test_txt_parse_chapter_count() -> None:
    chapters = _parse(_SIMPLE_TEXT)
    assert len(chapters) == 2


def test_txt_parse_paragraph_count() -> None:
    chapters = _parse(_SIMPLE_TEXT)
    assert len(chapters[0].paragraphs) == 2
    assert len(chapters[1].paragraphs) == 1


def test_txt_parse_paragraph_text() -> None:
    chapters = _parse(_SIMPLE_TEXT)
    assert chapters[0].paragraphs[0].text == "The hero walked into the forest."
    assert chapters[0].paragraphs[1].text == "She carried a sword."


def test_txt_parse_chapter_titles() -> None:
    chapters = _parse(_SIMPLE_TEXT)
    assert chapters[0].title == "Chapter 1"
    assert chapters[1].title == "Chapter 2"


def test_txt_parse_indexes_sequential() -> None:
    chapters = _parse(_SIMPLE_TEXT)
    for ch in chapters:
        for i, p in enumerate(ch.paragraphs):
            assert p.index == i


def test_txt_parse_no_chapter_markers() -> None:
    text = "Paragraph one.\n\nParagraph two."
    chapters = _parse(text)
    assert len(chapters) == 1
    assert len(chapters[0].paragraphs) == 2


def test_txt_adapter_load_from_file() -> None:
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(_SIMPLE_TEXT)
        path = Path(f.name)
    try:
        adapter = TxtAdapter()
        chapters = adapter.load(path)
        assert len(chapters) == 2
    finally:
        path.unlink()


def test_txt_adapter_paragraph_index_validity() -> None:
    chapters = _parse(_SIMPLE_TEXT)
    for ch in chapters:
        texts = [p.text for p in ch.paragraphs]
        assert all(t for t in texts), "No empty paragraphs expected"


# --- txt output adapter ---

def test_txt_output_roundtrip() -> None:
    ch = make_chapter(["First paragraph.", "Second paragraph."])
    adapter = TxtOutputAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "output.txt"
        adapter.write([ch], dest)
        content = dest.read_text(encoding="utf-8")
    assert "First paragraph." in content
    assert "Second paragraph." in content
    assert ch.title in content


def test_txt_output_creates_parent_dirs() -> None:
    ch = make_chapter(["Hello world."])
    adapter = TxtOutputAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "subdir" / "deep" / "out.txt"
        adapter.write([ch], dest)
        assert dest.exists()
