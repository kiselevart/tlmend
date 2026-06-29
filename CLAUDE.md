# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`tlmend` is a source-, format-, and provider-agnostic CLI tool that takes an existing translation and runs a configurable LLM pass to fix grammar, spelling, and awkward phrasing without changing meaning or terminology. It outputs a corrected version (EPUB / static site / text) plus a full audit trail. Reverend Insanity ships only as an example config + glossary — never as bundled text.

The detailed design lives in `docs/tl-mend-SDLC-plan.md`; that file is the source of truth for anything not covered here.

## Commands

```bash
# install (creates .venv/)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# run a project (mode via flag or config)
.venv/bin/tlmend run examples/reverend-insanity --mode review
.venv/bin/tlmend run examples/reverend-insanity --mode edit --policy report

# dry-run cost estimate for a chapter range
.venv/bin/tlmend estimate examples/reverend-insanity --range 1-50

# tests / lint / types
.venv/bin/pytest
.venv/bin/pytest tests/test_diff_classify.py::test_substantive_word_change   # single test
.venv/bin/ruff check .
.venv/bin/mypy tlmend
```

## Pipeline architecture

```
ingest → edit(LLM) → diff+classify ──┬─ mechanical ─► auto-apply
                                     └─ substantive ─► [MODE] ─► apply → validate → assemble
```

**Two modes, one pipeline:**
- `edit` — single-pass, no reviewer. Substantive hunks resolved by policy: `trust` (apply all), `report` (apply + log for human review), or `conservative` (keep original for substantive hunks).
- `review` — two-pass. Substantive hunks go to a reviewer LLM → accept/reject/modify.

Mechanical auto-apply and all validation gates are identical in both modes. The mode branch lives **only** in `pipeline/resolve.py` — nothing else knows which mode is active.

**Chapter status machine:** `pending → edited → diffed → resolved → validated → assembled` (plus `failed`/`flagged`). The orchestrator must resume cleanly after a kill; every stage commits to SQLite before advancing status.

## Repo layout

```
tlmend/
  adapters/input/      # epub, txt, markdown, html-dir, json → canonical chapters
  adapters/output/     # epub, static-site, text, diff-report
  providers/           # deepseek, anthropic, openai-compatible (one async interface)
  pipeline/            # ingest, edit, diff_classify, resolve, validate, assemble
  pipeline/resolve.py  # THE mode branch lives here and only here
  store/               # SQLite schema + access
  glossary/            # auto-seed + load/validate
  cli.py               # typer entrypoint
docs/tl-mend-SDLC-plan.md
examples/reverend-insanity/   # config.toml + glossary.json ONLY (source/ gitignored)
tests/
```

## Conventions

- Python 3.11+, type hints throughout, async for all LLM/network I/O via `httpx`. Bounded `asyncio.Semaphore` for concurrency; never fire unbounded requests.
- Adapters are the only code that knows file formats. The pipeline operates on canonical chapters (`id`, `title`, ordered paragraphs) exclusively.
- Providers sit behind one interface, bound by role (`editor`/`reviewer`) in config. Adding a provider must not touch pipeline code.
- Prompts are versioned and per-project. A prompt change is a re-processable event; record `prompt_version` in runs.
- Cost is first-class: log tokens + computed cost per call; support a dry-run estimator and a per-run cost cap that aborts on overrun.
- Diff + classify is pure `difflib` — no LLM. Given the same edited text, classification is reproducible.

## Non-negotiable invariants

These are correctness guarantees enforced by tests:

- **Content preservation.** The editor must never add, remove, or reinterpret content. Output contract: equal paragraph count to input — mismatch = reject and retry, never ship.
- **No silent deletion.** Any deletion or paragraph that shrinks past threshold is forced to "substantive" and (in review mode) always adjudicated. Validation rejects mass-shrink.
- **Glossary integrity.** Every glossary term present in the source must still be present in the final text.
- **Auditability.** Every final span traces original → proposed → decision → mode → prompt version via the SQLite store.
- **Clean repo.** No copyrighted content committed, ever. `examples/*/source/` is gitignored.

If a change would weaken any of these, stop and flag it rather than implementing.

## Testing expectations

- Unit: adapter paragraph fidelity; diff classification (crafted hunks → expected class); each substantive policy branch; validation gates.
- Content-preservation: synthetic "editor dropped a sentence" input must be flagged, never shipped.
- Mode parity: same chapter through edit and review — both pass validation; review never drops content that edit/conservative preserved.
- Golden set: ~15 representative paragraphs with known-good edits; run on any prompt/model change to catch regressions.
- No test may hit a live LLM API; mock the provider interface.

## Build order

Follow the SDLC phases: scaffold → ingest+glossary → single-chapter edit MVP → add review → tune on sample → batch orchestration → output writers → OSS polish. Get one chapter fully correct in edit mode before building breadth.

## Don't

- Bundle or commit any copyrighted source text.
- Let format/provider details leak into the pipeline.
- Use an LLM where deterministic code suffices (routing, validation).
- Apply substantive changes in review mode without a recorded reviewer decision.
- Advance chapter status before the stage's writes are committed.
