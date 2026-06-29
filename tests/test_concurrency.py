"""Concurrency tests — no LLM, measures wall time against a sleeping mock."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from tlmend.models import Chapter, CompletionResult, Paragraph, RunConfig
from tlmend.pipeline.orchestrator import run_pipeline
from tlmend.providers.base import Message
from tlmend.store.db import Store

_DELAY = 0.08   # seconds per simulated LLM call
_N = 8          # chapters


def _chapters(n: int) -> list[Chapter]:
    return [
        Chapter(id=str(i), title=f"Ch {i}", paragraphs=[Paragraph(index=0, text=f"Text {i}.")])
        for i in range(n)
    ]


def _cfg(tmp_path: Path, concurrency: int) -> RunConfig:
    return RunConfig(
        project_dir=str(tmp_path),
        mode="edit",
        policy="trust",
        concurrency=concurrency,
        cost_cap_usd=None,
        prompt_version="v1",
    )


class TimedProvider:
    """Provider that sleeps for a fixed delay and tracks peak concurrency."""

    def __init__(self, delay: float) -> None:
        self._delay = delay
        self._active = 0
        self.peak_active = 0
        self.call_count = 0

    async def complete(self, messages: list[Message], *, prompt_version: str) -> CompletionResult:
        self._active += 1
        self.peak_active = max(self.peak_active, self._active)
        self.call_count += 1
        await asyncio.sleep(self._delay)
        self._active -= 1
        # Return a valid numbered response matching the single-paragraph chapter
        return CompletionResult(
            text="[1] Corrected text.",
            prompt_tokens=10,
            completion_tokens=5,
            model="mock",
            prompt_version=prompt_version,
            cost_usd=0.0,
        )


async def test_full_concurrency_runs_in_parallel(tmp_path: Path) -> None:
    """All N chapters with concurrency=N should finish in ~1× delay, not N×."""
    provider = TimedProvider(_DELAY)
    cfg = _cfg(tmp_path, concurrency=_N)

    start = time.monotonic()
    async with Store(tmp_path / "run.sqlite") as store:
        assembled = await run_pipeline(_chapters(_N), provider, None, cfg, store, [])
    elapsed = time.monotonic() - start

    assert len(assembled) == _N
    assert provider.call_count == _N
    # All N calls were in flight simultaneously
    assert provider.peak_active == _N, f"expected peak={_N}, got {provider.peak_active}"
    # Wall time close to a single delay, not N delays
    assert elapsed < _DELAY * 3, f"took {elapsed:.2f}s — expected < {_DELAY * 3:.2f}s (parallel)"


async def test_concurrency_1_is_sequential(tmp_path: Path) -> None:
    """concurrency=1 must serialize all LLM calls."""
    provider = TimedProvider(_DELAY)
    cfg = _cfg(tmp_path, concurrency=1)

    start = time.monotonic()
    async with Store(tmp_path / "run.sqlite") as store:
        assembled = await run_pipeline(_chapters(_N), provider, None, cfg, store, [])
    elapsed = time.monotonic() - start

    assert len(assembled) == _N
    assert provider.peak_active == 1, f"expected peak=1, got {provider.peak_active}"
    # Wall time must be at least most of N × delay
    assert elapsed >= _DELAY * _N * 0.7, f"took {elapsed:.2f}s — expected >= {_DELAY * _N * 0.7:.2f}s (sequential)"


async def test_concurrency_partial_batching(tmp_path: Path) -> None:
    """concurrency=4 with 8 chapters: peak=4, time ~2× delay."""
    provider = TimedProvider(_DELAY)
    cfg = _cfg(tmp_path, concurrency=4)

    start = time.monotonic()
    async with Store(tmp_path / "run.sqlite") as store:
        assembled = await run_pipeline(_chapters(_N), provider, None, cfg, store, [])
    elapsed = time.monotonic() - start

    assert len(assembled) == _N
    assert provider.peak_active == 4, f"expected peak=4, got {provider.peak_active}"
    # Should be roughly 2× delay (two batches of 4)
    assert elapsed < _DELAY * 5, f"took {elapsed:.2f}s — too slow for concurrency=4"
    assert elapsed >= _DELAY * 1.5, f"took {elapsed:.2f}s — suspiciously fast for concurrency=4"


async def test_output_order_preserved(tmp_path: Path) -> None:
    """Assembled chapters must be in input order even when tasks finish out of order."""
    delays = [0.05, 0.01, 0.08, 0.02, 0.06, 0.01, 0.07, 0.03]

    class VariableDelayProvider:
        def __init__(self) -> None:
            self._call = 0

        async def complete(self, messages: list[Message], *, prompt_version: str) -> CompletionResult:
            idx = self._call
            self._call += 1
            await asyncio.sleep(delays[idx % len(delays)])
            return CompletionResult(
                text="[1] Corrected text.",
                prompt_tokens=10, completion_tokens=5,
                model="mock", prompt_version=prompt_version, cost_usd=0.0,
            )

    cfg = _cfg(tmp_path, concurrency=_N)
    async with Store(tmp_path / "run.sqlite") as store:
        assembled = await run_pipeline(
            _chapters(_N), VariableDelayProvider(), None, cfg, store, []
        )

    assert [ch.id for ch in assembled] == [str(i) for i in range(_N)]
