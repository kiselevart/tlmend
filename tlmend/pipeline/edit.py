"""Editor stage — sends a chapter to the editor LLM and returns edited paragraph texts."""

from __future__ import annotations

import asyncio

from tlmend.models import Chapter, CompletionResult
from tlmend.providers.base import Message, Provider

_SYSTEM_PROMPT = """\
You are a professional translation editor. Your job is to improve the grammar, spelling, \
and phrasing of the provided translation without changing its meaning or content.

Rules:
- Do NOT add, remove, or reinterpret any content.
- Do NOT alter proper nouns, character names, or glossary terms.
- Paragraphs are numbered [1], [2], etc. Return each paragraph with its number prefix intact.
- Output ONLY the numbered paragraphs, one per line, nothing else.
- The count of numbered paragraphs in your output MUST equal the count in the input.
"""


async def edit_chapter(
    chapter: Chapter,
    editor: Provider,
    prompt_version: str,
    semaphore: asyncio.Semaphore,
) -> tuple[list[str], CompletionResult]:
    """Return (edited_paragraph_texts, completion_result)."""
    async with semaphore:
        result = await editor.complete(
            _build_messages(chapter),
            prompt_version=prompt_version,
        )
    paragraphs = _parse_response(result.text)
    return paragraphs, result


def _build_messages(chapter: Chapter) -> list[Message]:
    numbered = "\n".join(f"[{p.index + 1}] {p.text}" for p in chapter.paragraphs)
    return [
        Message(role="system", content=_SYSTEM_PROMPT),
        Message(role="user", content=f"Chapter: {chapter.title}\n\n{numbered}"),
    ]


def _parse_response(text: str) -> list[str]:
    import re
    paragraphs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\[(\d+)\]\s*(.*)", line)
        if m:
            paragraphs.append(m.group(2).strip())
    return paragraphs
