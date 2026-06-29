"""End-to-end EPUB output tests — no LLM, synthetic epub, deterministic."""

from __future__ import annotations

import zipfile
from pathlib import Path

from tests.conftest import MockProvider
from tlmend.adapters.input.epub import EpubAdapter
from tlmend.adapters.output.epub import EpubOutputAdapter
from tlmend.models import Chapter, Paragraph, RunConfig
from tlmend.pipeline.orchestrator import run_pipeline
from tlmend.store.db import Store

# ---------------------------------------------------------------------------
# Synthetic EPUB builder
# ---------------------------------------------------------------------------

_MIMETYPE = "application/epub+zip"

_CONTAINER_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="book.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

_OPF = """\
<?xml version="1.0" encoding="UTF-8"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="ch1" href="OEBPS/chapter1.html" media-type="application/xhtml+xml"/>
    <item id="ch2" href="OEBPS/chapter2.html" media-type="application/xhtml+xml"/>
    <item id="css" href="OEBPS/style.css" media-type="text/css"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>"""

_CSS = "body { font-family: serif; } p { margin: 0.5em 0; }"

def _xhtml(title: str, paras: list[str]) -> str:
    body = "\n".join(f"<p>{t}</p>" for t in paras)
    return f"""\
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>{title}</title></head>
<body>
<h2 class="chapter-title">{title}</h2>
{body}
</body>
</html>"""


def make_epub(path: Path) -> None:
    """Write a minimal 2-chapter EPUB2 to *path*."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), _MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("book.opf", _OPF)
        zf.writestr("OEBPS/style.css", _CSS)
        zf.writestr(
            "OEBPS/chapter1.html",
            _xhtml("Chapter 1: The Beginning", [
                "The hero walked slowly down the road.",
                "He had a sword in his hand.",
            ]),
        )
        zf.writestr(
            "OEBPS/chapter2.html",
            _xhtml("Chapter 2: The Middle", [
                "The hero fought the dragon.",
                "He won the battle bravely.",
            ]),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _numbered(*paras: str) -> str:
    return "\n".join(f"[{i+1}] {t}" for i, t in enumerate(paras))


def _load_output_chapter(epub_path: Path, chapter_id: str) -> Chapter:
    chapters = EpubAdapter().load(epub_path)
    return next(c for c in chapters if c.id == chapter_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_epub_output_mimetype_first_and_stored(tmp_path: Path) -> None:
    template = tmp_path / "src.epub"
    make_epub(template)
    ch = Chapter(id="0", title="Chapter 1: The Beginning", paragraphs=[
        Paragraph(index=0, text="The hero walked slowly down the road."),
        Paragraph(index=1, text="He had a sword in his hand."),
    ])
    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write([ch], out)

    with zipfile.ZipFile(out) as zf:
        assert zf.namelist()[0] == "mimetype", "mimetype must be first entry"
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED, "mimetype must be uncompressed"
        assert zf.read("mimetype").decode() == _MIMETYPE


def test_epub_output_preserves_doctype(tmp_path: Path) -> None:
    template = tmp_path / "src.epub"
    make_epub(template)
    ch = Chapter(id="0", title="Chapter 1: The Beginning", paragraphs=[
        Paragraph(index=0, text="The hero walked slowly down the road."),
        Paragraph(index=1, text="He had a sword in hand."),  # corrected
    ])
    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write([ch], out)

    with zipfile.ZipFile(out) as zf:
        content = zf.read("OEBPS/chapter1.html").decode("utf-8")

    assert "<!DOCTYPE" in content, "DOCTYPE must be preserved in output XHTML"
    assert "XHTML 1.1" in content, "XHTML 1.1 DOCTYPE must be preserved"


def test_epub_output_corrected_text_lands(tmp_path: Path) -> None:
    template = tmp_path / "src.epub"
    make_epub(template)
    ch = Chapter(id="0", title="Chapter 1: The Beginning", paragraphs=[
        Paragraph(index=0, text="The hero walked slowly down the road."),
        Paragraph(index=1, text="He had a sword in hand."),  # "his" removed
    ])
    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write([ch], out)

    result = _load_output_chapter(out, "0")
    assert result.paragraphs[0].text == "The hero walked slowly down the road."
    assert result.paragraphs[1].text == "He had a sword in hand."


def test_epub_output_uncorrected_chapter_passes_through(tmp_path: Path) -> None:
    template = tmp_path / "src.epub"
    make_epub(template)
    # Only write chapter 0 corrections; chapter 1 should be unchanged.
    ch = Chapter(id="0", title="Chapter 1: The Beginning", paragraphs=[
        Paragraph(index=0, text="The hero walked slowly down the road."),
        Paragraph(index=1, text="He had a sword in hand."),
    ])
    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write([ch], out)

    result = _load_output_chapter(out, "1")
    assert result.paragraphs[0].text == "The hero fought the dragon."
    assert result.paragraphs[1].text == "He won the battle bravely."


def test_epub_output_non_chapter_files_unchanged(tmp_path: Path) -> None:
    template = tmp_path / "src.epub"
    make_epub(template)
    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write([], out)

    with zipfile.ZipFile(out) as zf:
        assert zf.read("OEBPS/style.css").decode() == _CSS
        assert zf.read("book.opf").decode() == _OPF


def test_epub_output_all_original_files_present(tmp_path: Path) -> None:
    template = tmp_path / "src.epub"
    make_epub(template)
    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write([], out)

    with zipfile.ZipFile(template) as t, zipfile.ZipFile(out) as o:
        assert set(t.namelist()) == set(o.namelist())


async def test_epub_full_pipeline_e2e(tmp_path: Path) -> None:
    """Full pipeline: synthetic EPUB → run_pipeline (mock LLM) → EPUB output → validate."""
    template = tmp_path / "src.epub"
    make_epub(template)

    chapters = EpubAdapter().load(template)
    # chapters[0].id="0" = Chapter 1, chapters[1].id="1" = Chapter 2

    editor = MockProvider([
        _numbered(
            "The hero walked down the road.",   # shortened (mechanical)
            "He had a sword in hand.",           # "his" removed (mechanical)
        ),
        _numbered(
            "The hero fought the dragon.",       # unchanged
            "He won the battle bravely.",        # unchanged
        ),
    ])

    cfg = RunConfig(
        project_dir=str(tmp_path),
        mode="edit",
        policy="trust",
        concurrency=1,
        cost_cap_usd=None,
        prompt_version="v1",
    )

    db_path = tmp_path / "run.sqlite"
    async with Store(db_path) as store:
        assembled = await run_pipeline(chapters, editor, None, cfg, store, glossary_terms=[])

    assert len(assembled) == 2

    out = tmp_path / "out.epub"
    EpubOutputAdapter(template).write(assembled, out)

    # --- structural validity ---
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist()[0] == "mimetype"
        assert zf.read("mimetype").decode() == _MIMETYPE

    # --- DOCTYPE preserved in both chapters ---
    with zipfile.ZipFile(out) as zf:
        for ch_file in ("OEBPS/chapter1.html", "OEBPS/chapter2.html"):
            content = zf.read(ch_file).decode("utf-8")
            assert "<!DOCTYPE" in content, f"DOCTYPE missing in {ch_file}"

    # --- corrected text landed ---
    result = EpubAdapter().load(out)
    ch1 = next(c for c in result if c.id == "0")
    assert ch1.paragraphs[0].text == "The hero walked down the road."
    assert ch1.paragraphs[1].text == "He had a sword in hand."

    # --- non-chapter files unchanged ---
    with zipfile.ZipFile(out) as zf:
        assert zf.read("OEBPS/style.css").decode() == _CSS
