"""Provider protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from tlmend.models import CompletionResult


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class Provider(Protocol):
    """LLM provider interface. Implementations live in this package only."""

    async def complete(
        self,
        messages: list[Message],
        *,
        prompt_version: str,
    ) -> CompletionResult: ...
