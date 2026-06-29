# tlmend SDLC Plan

## Milestones

### M1 — Scaffold (complete)
- `pyproject.toml`, directory tree, all `__init__.py` stubs
- `models.py` — canonical `Chapter`, `Paragraph`, `Hunk`, `Resolution`, `CompletionResult`, `RunConfig`
- `TxtAdapter` (input), `TxtOutputAdapter` (output)
- `AnthropicProvider` + `OpenAICompatProvider` stubs (real HTTP, no mocks)
- `diff_classify.py` — pure difflib, fully tested
- `validate.py` — four invariant gates, fully tested
- `resolve.py` — mode branch (edit policies + review LLM path), fully tested
- `edit.py` — editor stage stub
- `assemble.py` — assembly stage stub
- `store/db.py` — SQLite schema + `Store` async context manager
- `glossary/loader.py` — load + validate
- `cli.py` — `tlmend run` + `tlmend estimate` (scaffold stubs, no orchestrator yet)
- `examples/reverend-insanity/config.toml` + `glossary.json`
- Full test suite (50+ tests, zero live LLM calls)

### M2 — Single-chapter edit MVP
Goal: one chapter in, one corrected chapter out, full audit trail written.

- `pipeline/orchestrator.py` — async orchestrator wiring all stages end-to-end
- Wire `cli.py run` to real orchestrator
- `Store` write paths for edits, hunks, resolutions
- Cost cap enforcement (abort if `total_cost > cost_cap_usd`)
- Retry logic: if paragraph count mismatches, retry up to N times before flagging
- Integration test: mock provider, assert chapter status reaches ASSEMBLED

### M3 — Review mode
Goal: substantive hunks go to reviewer LLM, decisions recorded.

- `resolve_review` already scaffolded — integration test end-to-end
- Reviewer prompt refinement
- `Store` write path for `resolutions` table
- Mode parity test: same chapter through edit and review produces valid output

### M4 — Batch orchestration
Goal: process all chapters in a project concurrently with resume after crash.

- `orchestrator.py` iterates chapters, respects `asyncio.Semaphore(concurrency)`
- Chapter status machine in SQLite — resume skips non-pending chapters
- Chapter range filtering (`--range 1-50`)
- Progress reporting via `rich`

### M5 — Output writers + cost estimation
- `EpubOutputAdapter` (stub → real)
- `DiffReportOutputAdapter` — markdown diff report
- `tlmend estimate` — count paragraphs × estimated tokens → cost per model
- `StaticSiteOutputAdapter` (stretch)

### M6 — OSS polish
- Proper README with quickstart
- `examples/reverend-insanity/` end-to-end smoke test (real LLM, gated by env var)
- `ruff` + `mypy --strict` clean
- GitHub Actions CI

## Key design decisions

### Why SQLite + aiosqlite
Single-file, crash-safe, zero infrastructure. Every stage commits before advancing
chapter status, so a kill mid-run leaves a clean resume point.

### Why difflib not an LLM for diff/classify
Deterministic. Given the same edited text, classification is reproducible and testable
without any network calls.

### Why `resolve.py` is the only mode-aware file
Everything else is mode-agnostic. Keeping the mode branch isolated makes it easy to
test each policy without a full orchestrator and prevents mode logic from leaking into
adapters or providers.

### Why paragraph count equality is the output contract
It is the simplest invariant that prevents content deletion. The LLM is instructed to
return the same number of blank-line-delimited blocks as the input. Any mismatch
triggers a retry, not a silent crop.
