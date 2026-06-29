"""Plain-text input adapter.

Chapters are delimited by lines matching ``CHAPTER_PATTERN``; paragraphs by
blank lines.
"""

from __future__ import annotations

import re
from pathlib import Path

from tlmend.adapters.input.base import InputAdapter
from tlmend.models import Chapter, Paragraph

CHAPTER_PATTERN = re.compile(r"^chapter\s+\d+", re.IGNORECASE)


class TxtAdapter(InputAdapter):
    def load(self, path: Path) -> list[Chapter]:
        text = path.read_text(encoding="utf-8")
        return _parse(text)


def _parse(text: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    current_title = "Chapter 1"
    current_blocks: list[str] = []
    chapter_index = 0

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        if CHAPTER_PATTERN.match(line.strip()):
            if current_blocks:
                chapters.append(_make_chapter(chapter_index, current_title, current_blocks))
                chapter_index += 1
                current_blocks = []
            current_title = line.strip()
        else:
            current_blocks.append(line)

    if current_blocks:
        chapters.append(_make_chapter(chapter_index, current_title, current_blocks))

    return chapters


def _make_chapter(index: int, title: str, lines: list[str]) -> Chapter:
    raw = "\n".join(lines)
    blocks = [b.strip() for b in re.split(r"\n{2,}", raw)]
    paragraphs = [
        Paragraph(index=i, text=b)
        for i, b in enumerate(blocks)
        if b
    ]
    return Chapter(id=str(index), title=title, paragraphs=paragraphs)
