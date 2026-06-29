"""Integration tests for the orchestrator.

Uses a real SQLite store (temp file) and MockProvider — no live LLM calls.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tlmend.models import Chapter, ChapterStatus, RunConfig
from tlmend.pipeline.orchestrator import CostCapExceeded, run_pipeline
from tlmend.store.db import Store
from tests.conftest import MockProvider, make_chapter


def _cfg(mode: str = "edit", policy: str = "report", cost_cap: float | None = None) -> RunConfig:
    return RunConfig(
        project_dir="/tmp/test-project",
        mode=mode,  # type: ignore[arg-type]
        policy=policy,  # type: ignore[arg-type]
        concurrency=2,
        cost_cap_usd=cost_cap,
        prompt_version="v1",
    )


def _edited(chapter: Chapter) -> str:
    """Build a valid mock edit response in numbered format: [1] para [2] para ..."""
    return "\n".join(f"[{p.index + 1}] {p.text.replace('.', '!')}" for p in chapter.paragraphs)


# --- happy path ---

async def test_single_chapter_reaches_assembled() -> None:
    chapter = make_chapter(["The hero walked.", "She was brave."])
    mock = MockProvider([_edited(chapter)])

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        assembled = await run_pipeline([chapter], mock, None, _cfg(), store, [])

    assert len(assembled) == 1
    assert len(assembled[0].paragraphs) == 2


async def test_assembled_chapter_has_correct_paragraph_count() -> None:
    chapter = make_chapter(["Para one.", "Para two.", "Para three."])
    mock = MockProvider([_edited(chapter)])

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        assembled = await run_pipeline([chapter], mock, None, _cfg(), store, [])

    assert len(assembled[0].paragraphs) == 3


async def test_audit_trail_written_to_store() -> None:
    chapter = make_chapter(["The hero walked.", "She was brave."])
    mock = MockProvider([_edited(chapter)])

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        await run_pipeline([chapter], mock, None, _cfg(), store, [])

        row = await (await store._conn.execute(
            "SELECT status FROM chapters WHERE chapter_id=?", (chapter.id,)
        )).fetchone()
        assert row is not None
        assert row[0] == ChapterStatus.ASSEMBLED

        edits_count = (await (await store._conn.execute(
            "SELECT COUNT(*) FROM edits"
        )).fetchone())[0]
        assert edits_count == 1

        cost_rows = (await (await store._conn.execute(
            "SELECT COUNT(*) FROM cost_log"
        )).fetchone())[0]
        assert cost_rows >= 1


async def test_multiple_chapters_all_assembled() -> None:
    chapters = [
        make_chapter(["Chapter one, para one."], chapter_id="c1", title="Chapter 1"),
        make_chapter(["Chapter two, para one."], chapter_id="c2", title="Chapter 2"),
    ]
    responses = [_edited(ch) for ch in chapters]
    mock = MockProvider(responses)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        assembled = await run_pipeline(chapters, mock, None, _cfg(), store, [])

    assert len(assembled) == 2


# --- retry on paragraph count mismatch ---

async def test_retry_on_paragraph_mismatch_then_succeeds() -> None:
    chapter = make_chapter(["Para one.", "Para two."])
    bad_response = "Only one paragraph returned."
    good_response = _edited(chapter)
    mock = MockProvider([bad_response, good_response])

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        assembled = await run_pipeline([chapter], mock, None, _cfg(), store, [])

    assert len(assembled) == 1
    assert len(mock.calls) == 2  # first call returned wrong count, second succeeded


async def test_all_retries_exhausted_flags_chapter() -> None:
    chapter = make_chapter(["Para one.", "Para two."])
    bad_response = "Only one paragraph."
    mock = MockProvider([bad_response, bad_response, bad_response])

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        assembled = await run_pipeline([chapter], mock, None, _cfg(), store, [])
        assert assembled == []

        row = await (await store._conn.execute(
            "SELECT status FROM chapters WHERE chapter_id=?", (chapter.id,)
        )).fetchone()
        assert row[0] == ChapterStatus.FLAGGED


# --- cost cap ---

async def test_cost_cap_aborts_pipeline() -> None:
    chapters = [
        make_chapter(["Para."], chapter_id="c1", title="Chapter 1"),
        make_chapter(["Para."], chapter_id="c2", title="Chapter 2"),
    ]
    responses = [_edited(ch) for ch in chapters]
    mock = MockProvider(responses)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    # MockProvider returns cost_usd=0.0, so cap of 0.0 means it triggers after first log
    # Force trigger by setting a cap of -1.0 (always exceeded)
    cfg = _cfg(cost_cap=-1.0)

    async with Store(store_path) as store:
        with pytest.raises(CostCapExceeded):
            await run_pipeline(chapters, mock, None, cfg, store, [])


# --- resume ---

async def test_resume_skips_assembled_chapter() -> None:
    """Simulate a crash: chapter is ASSEMBLED but run.ended_at is NULL.
    A second invocation must reuse the same run and skip the already-assembled chapter."""
    chapter = make_chapter(["Para one."], chapter_id="resume-c1")
    mock = MockProvider([])  # zero responses — chapter must not be re-processed

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    cfg = _cfg()

    # Manually construct the "crashed mid-run" state.
    async with Store(store_path) as store:
        run_id = await store.create_run(
            cfg.project_dir, cfg.mode, cfg.policy, cfg.prompt_version, "2026-01-01T00:00:00"
        )
        ch_row_id, _ = await store.get_or_create_chapter(run_id, chapter.id, chapter.title)
        await store.set_chapter_status(ch_row_id, ChapterStatus.ASSEMBLED)
        # ended_at intentionally left NULL — simulates process killed after assembling

    # Resume: find_or_create_run finds the incomplete run; chapter is ASSEMBLED → skip.
    async with Store(store_path) as store:
        await run_pipeline([chapter], mock, None, cfg, store, [])

    assert len(mock.calls) == 0  # provider never called


# --- glossary validation ---

async def test_glossary_term_removed_flags_chapter() -> None:
    chapter = make_chapter(["Reverend Insanity spoke."])
    # Mock editor removes the glossary term on all MAX_VALIDATION_RETRIES attempts
    mock = MockProvider(["[1] The protagonist spoke."] * 3)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    async with Store(store_path) as store:
        assembled = await run_pipeline([chapter], mock, None, _cfg(), store, ["Reverend Insanity"])

    assert assembled == []

    async with Store(store_path) as store:
        row = await (await store._conn.execute(
            "SELECT status FROM chapters WHERE chapter_id=?", (chapter.id,)
        )).fetchone()
        assert row[0] == ChapterStatus.FLAGGED


# --- conservative policy keeps substantive hunks ---

async def test_conservative_policy_keeps_original_for_substantive() -> None:
    chapter = make_chapter(["The hero walked slowly into the dark forest."])
    # Editor makes a substantive change (adds word "ominous")
    mock = MockProvider(["[1] The hero walked slowly into the ominous dark forest."])

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = Path(f.name)

    cfg = _cfg(policy="conservative")
    async with Store(store_path) as store:
        assembled = await run_pipeline([chapter], mock, None, cfg, store, [])

    assert len(assembled) == 1
    # conservative keeps original for substantive changes
    assert assembled[0].paragraphs[0].text == "The hero walked slowly into the dark forest."
