"""Shared fixtures and mock provider."""

from __future__ import annotations

import pytest

from tlmend.models import Chapter, CompletionResult, Paragraph
from tlmend.providers.base import Message


def make_chapter(paragraphs: list[str], chapter_id: str = "c1", title: str = "Chapter 1") -> Chapter:
    return Chapter(
        id=chapter_id,
        title=title,
        paragraphs=[Paragraph(index=i, text=t) for i, t in enumerate(paragraphs)],
    )


class MockProvider:
    """Provider that returns pre-configured responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[list[Message]] = []

    async def complete(self, messages: list[Message], *, prompt_version: str) -> CompletionResult:
        self.calls.append(messages)
        if self._index >= len(self._responses):
            raise RuntimeError("MockProvider ran out of responses")
        text = self._responses[self._index]
        self._index += 1
        return CompletionResult(
            text=text,
            prompt_tokens=100,
            completion_tokens=50,
            model="mock",
            prompt_version=prompt_version,
            cost_usd=0.0,
        )


@pytest.fixture
def sample_chapter() -> Chapter:
    return make_chapter([
        "The hero walked slowly into the dark forest.",
        "She carried a sword of ancient design.",
        "Reverend Insanity watched from the shadows.",
    ])
