"""Canonical data models shared across all pipeline stages."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Literal


class ChapterStatus(str, enum.Enum):
    PENDING = "pending"
    EDITED = "edited"
    DIFFED = "diffed"
    RESOLVED = "resolved"
    VALIDATED = "validated"
    ASSEMBLED = "assembled"
    FAILED = "failed"
    FLAGGED = "flagged"


class HunkClass(str, enum.Enum):
    MECHANICAL = "mechanical"   # punctuation, whitespace, capitalisation
    SUBSTANTIVE = "substantive" # meaning-bearing change


class Decision(str, enum.Enum):
    APPLY = "apply"
    KEEP = "keep"       # retain original
    MODIFY = "modify"   # reviewer supplied alternate text


@dataclass
class Paragraph:
    index: int          # 0-based position within chapter
    text: str


@dataclass
class Chapter:
    id: str
    title: str
    paragraphs: list[Paragraph]

    def __post_init__(self) -> None:
        for i, p in enumerate(self.paragraphs):
            if p.index != i:
                raise ValueError(f"Paragraph index mismatch at position {i}: got {p.index}")


@dataclass
class Hunk:
    index: int          # paragraph index
    original: str
    proposed: str
    classification: HunkClass


@dataclass
class Resolution:
    hunk: Hunk
    decision: Decision
    final_text: str     # the text that will appear in output
    reason: str = ""    # reviewer explanation or policy name


@dataclass
class CompletionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    prompt_version: str
    cost_usd: float = 0.0


@dataclass
class ChapterResult:
    chapter_id: str
    title: str
    status: ChapterStatus
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    attempts: int                # edit retries used
    hunks_mechanical: int
    hunks_substantive: int
    decisions_applied: int
    decisions_kept: int
    validation_errors: list[str]


@dataclass
class RunConfig:
    project_dir: str
    mode: Literal["edit", "review"]
    policy: Literal["trust", "report", "conservative"] = "report"
    concurrency: int = 4
    cost_cap_usd: float | None = None
    prompt_version: str = "v1"
    dry_run: bool = False
