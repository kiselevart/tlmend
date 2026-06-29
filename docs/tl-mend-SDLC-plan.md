# tlmend SDLC Plan

## Milestones

### M1 — Scaffold ✅
- `pyproject.toml`, directory tree, all `__init__.py` stubs
- `models.py` — canonical `Chapter`, `Paragraph`, `Hunk`, `Resolution`, `CompletionResult`, `RunConfig`
- `TxtAdapter` (input), `TxtOutputAdapter` (output)
- `AnthropicProvider` + `OpenAICompatProvider` + `DeepSeekProvider`
- `diff_classify.py` — pure difflib, fully tested
- `validate.py` — four invariant gates, fully tested
- `resolve.py` — mode branch (edit policies + review LLM path), fully tested
- `edit.py` — editor stage with numbered paragraph format `[1] para`
- `assemble.py` — assembly stage
- `store/db.py` — SQLite schema + `Store` async context manager
- `glossary/loader.py` — load + validate
- `cli.py` — `tlmend run` + `tlmend estimate` (stub)
- `examples/reverend-insanity/config.toml` + `glossary.json`
- 70 tests, zero live LLM calls

### M2 — Single-chapter edit MVP ✅
- `pipeline/orchestrator.py` — async orchestrator wiring all stages end-to-end
- Full `cli.py run` with rich progress output per chapter
- Cost cap enforcement + retry on paragraph-count mismatch (MAX_EDIT_RETRIES=3)
- Resume: skips ASSEMBLED and FLAGGED chapters on re-run

### M3 — Review mode ✅
- `resolve_review` end-to-end integration tested
- Mode parity test: same chapter through edit and review produces valid output

### M4 — Batch orchestration + concurrency ✅
- `asyncio.gather` fan-out (was sequential for loop — fixed)
- `asyncio.Semaphore(concurrency)` gates LLM calls
- 429 rate-limit retry with exponential backoff in `OpenAICompatProvider`
- `--range`, `--concurrency` / `-j` CLI flags
- `--retry-flagged` flag + `reopen_best_run` for safe reruns
- Concurrency tests: wall-time + peak-active assertions (4 tests, no LLM)

### M5 — Output writers ✅
- `EpubOutputAdapter`: patches original epub in-place
  - Preserves CSS, fonts, images, cover, NCX, metadata exactly
  - DOCTYPE preserved via preamble splice (ET strips it)
  - `_is_meta_paragraph()` shared with input adapter (translator credits, plain title repeats)
- 7 E2E epub tests (synthetic epub, MockProvider, no LLM)
- README with quickstart, provider table, settings reference

### M6 — OSS polish (next)
- `tlmend estimate` — count paragraphs × estimated tokens → cost per model (currently a stub)
- `DiffReportOutputAdapter` — markdown diff report of all changes
- `StaticSiteOutputAdapter` (stretch)
- GitHub Actions CI
- `ruff` + `mypy --strict` clean pass

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
Simplest invariant preventing content deletion. Numbered format `[1] para` makes
boundaries unambiguous. Mismatch triggers retry, not silent crop.

### Why EpubOutputAdapter patches in-place
Preserves all non-text content (CSS, fonts, cover, NCX) without any knowledge of EPUB
internals beyond OPF spine order. Only `<p>` text content changes; everything else is
bitwise identical to the source.

### DeepSeek V4-Flash thinking tokens
Thinking/chain-of-thought is ON by default. Always pass `{"thinking": {"type": "disabled"}}`
for grammar correction — 4× cost otherwise. Controlled via `DeepSeekProvider(thinking=False)`.

### EPUB chapter id = spine index
`EpubAdapter` assigns `chapter_id = str(spine_index)`. For Reverend Insanity:
front-cover(0), title-page(1, "Information"), TOC(2, skipped), page-0(3, "Chapter 1")...
Use `--range 2-501` to process the 500 actual novel chapters.

## Prompt rules (edit.py)
- Do NOT add, remove, or reinterpret content
- Do NOT alter proper nouns, character names, glossary terms
- **NEVER replace a character name with a pronoun** (e.g. keep "Fang Yuan", never "He")
- Paragraphs numbered `[1]`, `[2]` — return with prefix intact, one per line
- Output count MUST equal input count
