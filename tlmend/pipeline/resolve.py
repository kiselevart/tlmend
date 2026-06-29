"""Mode branch — the ONLY place that knows whether we are in edit or review mode.

edit mode  → resolve via policy (trust / report / conservative)
review mode → send substantive hunks to the reviewer LLM
"""

from __future__ import annotations

import asyncio
from typing import Literal, assert_never

from tlmend.models import Decision, Hunk, HunkClass, Resolution
from tlmend.providers.base import Message, Provider


Policy = Literal["trust", "report", "conservative"]


async def resolve_edit(
    hunks: list[Hunk],
    policy: Policy,
) -> list[Resolution]:
    """Resolve hunks using a policy (no reviewer LLM)."""
    resolutions: list[Resolution] = []
    for hunk in hunks:
        if hunk.classification == HunkClass.MECHANICAL:
            resolutions.append(Resolution(
                hunk=hunk,
                decision=Decision.APPLY,
                final_text=hunk.proposed,
                reason="mechanical",
            ))
        else:
            resolutions.append(_apply_policy(hunk, policy))
    return resolutions


async def resolve_review(
    hunks: list[Hunk],
    reviewer: Provider,
    prompt_version: str,
    semaphore: asyncio.Semaphore,
) -> list[Resolution]:
    """Resolve hunks by sending substantive ones to the reviewer LLM."""
    tasks = [
        _resolve_one(hunk, reviewer, prompt_version, semaphore)
        for hunk in hunks
    ]
    return list(await asyncio.gather(*tasks))


async def _resolve_one(
    hunk: Hunk,
    reviewer: Provider,
    prompt_version: str,
    semaphore: asyncio.Semaphore,
) -> Resolution:
    if hunk.classification == HunkClass.MECHANICAL:
        return Resolution(
            hunk=hunk,
            decision=Decision.APPLY,
            final_text=hunk.proposed,
            reason="mechanical",
        )

    async with semaphore:
        result = await reviewer.complete(
            _reviewer_messages(hunk),
            prompt_version=prompt_version,
        )

    decision, final_text = _parse_reviewer_response(result.text, hunk)
    return Resolution(
        hunk=hunk,
        decision=decision,
        final_text=final_text,
        reason=result.text[:200],
    )


def _apply_policy(hunk: Hunk, policy: Policy) -> Resolution:
    match policy:
        case "trust":
            return Resolution(hunk=hunk, decision=Decision.APPLY, final_text=hunk.proposed, reason="trust")
        case "conservative":
            return Resolution(hunk=hunk, decision=Decision.KEEP, final_text=hunk.original, reason="conservative")
        case "report":
            return Resolution(hunk=hunk, decision=Decision.APPLY, final_text=hunk.proposed, reason="report")
        case _:
            assert_never(policy)


def _reviewer_messages(hunk: Hunk) -> list[Message]:
    return [
        Message(role="system", content=(
            "You are a translation quality reviewer. "
            "Decide whether to ACCEPT or REJECT the proposed edit. "
            "Reply with exactly: ACCEPT or REJECT, then a newline, then one sentence of reasoning."
        )),
        Message(role="user", content=(
            f"ORIGINAL:\n{hunk.original}\n\nPROPOSED:\n{hunk.proposed}"
        )),
    ]


def _parse_reviewer_response(text: str, hunk: Hunk) -> tuple[Decision, str]:
    first_line = text.strip().splitlines()[0].strip().upper()
    if first_line.startswith("ACCEPT"):
        return Decision.APPLY, hunk.proposed
    return Decision.KEEP, hunk.original
