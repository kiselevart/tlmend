"""Plain-text output adapter."""

from __future__ import annotations

from pathlib import Path

from tlmend.adapters.output.base import OutputAdapter
from tlmend.models import Chapter


class TxtOutputAdapter(OutputAdapter):
    def write(self, chapters: list[Chapter], dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for chapter in chapters:
            lines.append(chapter.title)
            lines.append("")
            for para in chapter.paragraphs:
                lines.append(para.text)
                lines.append("")
        dest.write_text("\n".join(lines), encoding="utf-8")
