"""Tests for resolve.py — mode branch."""

import asyncio

from tlmend.models import Decision, Hunk, HunkClass
from tlmend.pipeline.resolve import resolve_edit, resolve_review
from tests.conftest import MockProvider


def _make_hunk(index: int, classification: HunkClass, original: str = "orig", proposed: str = "prop") -> Hunk:
    return Hunk(index=index, original=original, proposed=proposed, classification=classification)


# --- edit mode ---

async def test_edit_mechanical_always_applied() -> None:
    hunks = [_make_hunk(0, HunkClass.MECHANICAL)]
    resolutions = await resolve_edit(hunks, policy="trust")
    assert resolutions[0].decision == Decision.APPLY
    assert resolutions[0].final_text == "prop"


async def test_edit_policy_trust_applies_substantive() -> None:
    hunks = [_make_hunk(0, HunkClass.SUBSTANTIVE)]
    resolutions = await resolve_edit(hunks, policy="trust")
    assert resolutions[0].decision == Decision.APPLY


async def test_edit_policy_conservative_keeps_substantive() -> None:
    hunks = [_make_hunk(0, HunkClass.SUBSTANTIVE)]
    resolutions = await resolve_edit(hunks, policy="conservative")
    assert resolutions[0].decision == Decision.KEEP
    assert resolutions[0].final_text == "orig"


async def test_edit_policy_report_applies_substantive() -> None:
    hunks = [_make_hunk(0, HunkClass.SUBSTANTIVE)]
    resolutions = await resolve_edit(hunks, policy="report")
    assert resolutions[0].decision == Decision.APPLY
    assert resolutions[0].reason == "report"


async def test_edit_mixed_hunks() -> None:
    hunks = [
        _make_hunk(0, HunkClass.MECHANICAL),
        _make_hunk(1, HunkClass.SUBSTANTIVE),
        _make_hunk(2, HunkClass.MECHANICAL),
    ]
    resolutions = await resolve_edit(hunks, policy="conservative")
    assert resolutions[0].decision == Decision.APPLY   # mechanical
    assert resolutions[1].decision == Decision.KEEP    # substantive + conservative
    assert resolutions[2].decision == Decision.APPLY   # mechanical


# --- review mode ---

async def test_review_accept_response() -> None:
    mock = MockProvider(["ACCEPT\nThe edit improves phrasing."])
    hunks = [_make_hunk(0, HunkClass.SUBSTANTIVE)]
    sem = asyncio.Semaphore(1)
    resolutions = await resolve_review(hunks, mock, "v1", sem)
    assert resolutions[0].decision == Decision.APPLY
    assert resolutions[0].final_text == "prop"
    assert len(mock.calls) == 1


async def test_review_reject_response() -> None:
    mock = MockProvider(["REJECT\nThe edit changes meaning."])
    hunks = [_make_hunk(0, HunkClass.SUBSTANTIVE)]
    sem = asyncio.Semaphore(1)
    resolutions = await resolve_review(hunks, mock, "v1", sem)
    assert resolutions[0].decision == Decision.KEEP
    assert resolutions[0].final_text == "orig"


async def test_review_mechanical_not_sent_to_llm() -> None:
    mock = MockProvider([])  # no responses needed
    hunks = [_make_hunk(0, HunkClass.MECHANICAL)]
    sem = asyncio.Semaphore(1)
    resolutions = await resolve_review(hunks, mock, "v1", sem)
    assert resolutions[0].decision == Decision.APPLY
    assert len(mock.calls) == 0  # no LLM call made


async def test_review_mixed_only_substantive_sent() -> None:
    mock = MockProvider(["ACCEPT\nOk."])
    hunks = [
        _make_hunk(0, HunkClass.MECHANICAL),
        _make_hunk(1, HunkClass.SUBSTANTIVE),
    ]
    sem = asyncio.Semaphore(2)
    resolutions = await resolve_review(hunks, mock, "v1", sem)
    assert resolutions[0].decision == Decision.APPLY
    assert resolutions[1].decision == Decision.APPLY
    assert len(mock.calls) == 1  # only 1 LLM call for the substantive hunk
