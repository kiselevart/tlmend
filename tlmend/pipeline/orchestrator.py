"""Single-chapter pipeline orchestrator.

Wires ingest → edit → diff_classify → resolve → validate → assemble and
maintains the chapter status machine in SQLite. Handles retry on paragraph
count mismatch and aborts on cost cap overrun.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from tlmend.models import Chapter, ChapterResult, ChapterStatus, CompletionResult, Decision, HunkClass, RunConfig
from tlmend.pipeline.assemble import assemble_chapter
from tlmend.pipeline.diff_classify import diff_chapter
from tlmend.pipeline.edit import edit_chapter
from tlmend.pipeline.resolve import resolve_edit, resolve_review
from tlmend.pipeline.validate import validate
from tlmend.providers.base import Provider
from tlmend.store.db import Store

MAX_EDIT_RETRIES = 3
MAX_VALIDATION_RETRIES = 3


class CostCapExceeded(Exception):
    """Raised when accumulated cost reaches the configured cap."""


async def run_pipeline(
    chapters: list[Chapter],
    editor: Provider,
    reviewer: Provider | None,
    config: RunConfig,
    store: Store,
    glossary_terms: list[str],
    on_chapter_done: Callable[[ChapterResult], None] | None = None,
) -> list[Chapter]:
    """Process *chapters* end-to-end and return assembled chapters.

    Reuses an in-progress run (resume after crash) or creates a new one.
    Calls *on_chapter_done* after each chapter regardless of outcome.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = await store.find_or_create_run(
        config.project_dir, config.mode, config.policy,
        config.prompt_version, started_at,
    )

    semaphore = asyncio.Semaphore(config.concurrency)
    assembled: list[Chapter | None] = [None] * len(chapters)

    async def _process(idx: int, chapter: Chapter) -> None:
        result, chapter_result = await _run_chapter(
            chapter, editor, reviewer, config, store, run_id, glossary_terms, semaphore
        )
        assembled[idx] = result
        if on_chapter_done is not None:
            on_chapter_done(chapter_result)

    # return_exceptions=True so all tasks finish before we inspect outcomes;
    # CostCapExceeded is re-raised after cleanup, other exceptions propagate.
    outcomes = await asyncio.gather(
        *[_process(idx, ch) for idx, ch in enumerate(chapters)],
        return_exceptions=True,
    )

    await store.finish_run(run_id)

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome

    return [ch for ch in assembled if ch is not None]


async def _run_chapter(
    chapter: Chapter,
    editor: Provider,
    reviewer: Provider | None,
    config: RunConfig,
    store: Store,
    run_id: int,
    glossary_terms: list[str],
    semaphore: asyncio.Semaphore,
) -> tuple[Chapter | None, ChapterResult]:
    def _result(
        status: ChapterStatus,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        attempts: int = 0,
        hunks_mechanical: int = 0,
        hunks_substantive: int = 0,
        decisions_applied: int = 0,
        decisions_kept: int = 0,
        validation_errors: list[str] | None = None,
    ) -> ChapterResult:
        return ChapterResult(
            chapter_id=chapter.id,
            title=chapter.title,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            attempts=attempts,
            hunks_mechanical=hunks_mechanical,
            hunks_substantive=hunks_substantive,
            decisions_applied=decisions_applied,
            decisions_kept=decisions_kept,
            validation_errors=validation_errors or [],
        )

    chapter_row_id, status = await store.get_or_create_chapter(run_id, chapter.id, chapter.title)

    if status in (ChapterStatus.ASSEMBLED, ChapterStatus.FLAGGED):
        return None, _result(ChapterStatus(status))

    edit_result: CompletionResult | None = None
    total_attempts = 0
    n_mechanical = n_substantive = n_applied = n_kept = 0
    assembled: Chapter | None = None
    val_errors: list[str] = []

    for val_round in range(1, MAX_VALIDATION_RETRIES + 1):
        # --- edit stage ---
        await _assert_cost_cap(store, run_id, config)
        edited_paragraphs, edit_result, attempt = await _edit_with_retry(
            chapter, editor, config, store, run_id, semaphore
        )
        total_attempts += attempt
        if edited_paragraphs is None:
            await store.set_chapter_status(chapter_row_id, ChapterStatus.FLAGGED)
            return None, _result(
                ChapterStatus.FLAGGED,
                prompt_tokens=edit_result.prompt_tokens,
                completion_tokens=edit_result.completion_tokens,
                cost_usd=edit_result.cost_usd,
                attempts=total_attempts,
                validation_errors=["paragraph count mismatch after all retries"],
            )

        original_text = "\n\n".join(p.text for p in chapter.paragraphs)
        proposed_text = "\n\n".join(edited_paragraphs)
        await store.write_edit(chapter_row_id, original_text, proposed_text, edit_result, total_attempts)
        await store.set_chapter_status(chapter_row_id, ChapterStatus.EDITED)

        # --- diff + classify ---
        hunks = diff_chapter(chapter, edited_paragraphs)
        hunk_ids = [await store.write_hunk(chapter_row_id, h) for h in hunks]
        await store.set_chapter_status(chapter_row_id, ChapterStatus.DIFFED)

        n_mechanical = sum(1 for h in hunks if h.classification == HunkClass.MECHANICAL)
        n_substantive = len(hunks) - n_mechanical

        # --- resolve ---
        if config.mode == "edit":
            resolutions = await resolve_edit(hunks, config.policy)
        else:
            if reviewer is None:
                raise ValueError("review mode requires a reviewer provider")
            await _assert_cost_cap(store, run_id, config)
            resolutions = await resolve_review(hunks, reviewer, config.prompt_version, semaphore)

        for hunk_id, resolution in zip(hunk_ids, resolutions):
            await store.write_resolution(hunk_id, resolution)
        await store.set_chapter_status(chapter_row_id, ChapterStatus.RESOLVED)

        n_applied = sum(1 for r in resolutions if r.decision == Decision.APPLY)
        n_kept = sum(1 for r in resolutions if r.decision == Decision.KEEP)

        # --- assemble + validate ---
        assembled = assemble_chapter(chapter, resolutions)
        val = validate(chapter, assembled, glossary_terms)
        if val.ok:
            break

        val_errors = val.errors
        if val_round < MAX_VALIDATION_RETRIES:
            await store.set_chapter_status(chapter_row_id, ChapterStatus.PENDING)
        else:
            await store.set_chapter_status(chapter_row_id, ChapterStatus.FLAGGED)
            return None, _result(
                ChapterStatus.FLAGGED,
                prompt_tokens=edit_result.prompt_tokens,
                completion_tokens=edit_result.completion_tokens,
                cost_usd=edit_result.cost_usd,
                attempts=total_attempts,
                hunks_mechanical=n_mechanical,
                hunks_substantive=n_substantive,
                decisions_applied=n_applied,
                decisions_kept=n_kept,
                validation_errors=val_errors,
            )

    assert edit_result is not None
    assert assembled is not None
    await store.set_chapter_status(chapter_row_id, ChapterStatus.VALIDATED)
    await store.set_chapter_status(chapter_row_id, ChapterStatus.ASSEMBLED)

    return assembled, _result(
        ChapterStatus.ASSEMBLED,
        prompt_tokens=edit_result.prompt_tokens,
        completion_tokens=edit_result.completion_tokens,
        cost_usd=edit_result.cost_usd,
        attempts=total_attempts,
        hunks_mechanical=n_mechanical,
        hunks_substantive=n_substantive,
        decisions_applied=n_applied,
        decisions_kept=n_kept,
    )


async def _edit_with_retry(
    chapter: Chapter,
    editor: Provider,
    config: RunConfig,
    store: Store,
    run_id: int,
    semaphore: asyncio.Semaphore,
) -> tuple[list[str] | None, CompletionResult, int]:
    last_result: CompletionResult | None = None
    for attempt in range(1, MAX_EDIT_RETRIES + 1):
        paragraphs, result = await edit_chapter(chapter, editor, config.prompt_version, semaphore)
        last_result = result
        await store.log_cost(
            run_id, "edit", result.model,
            result.prompt_tokens, result.completion_tokens, result.cost_usd,
        )
        if len(paragraphs) == len(chapter.paragraphs):
            return paragraphs, result, attempt
        if attempt < MAX_EDIT_RETRIES:
            await _assert_cost_cap(store, run_id, config)
    assert last_result is not None
    return None, last_result, MAX_EDIT_RETRIES


async def _assert_cost_cap(store: Store, run_id: int, config: RunConfig) -> None:
    if config.cost_cap_usd is None:
        return
    total = await store.total_cost(run_id)
    if total >= config.cost_cap_usd:
        raise CostCapExceeded(
            f"Cost cap ${config.cost_cap_usd:.2f} reached (accumulated ${total:.4f})"
        )
