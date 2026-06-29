# tlmend

A source-, format-, and provider-agnostic CLI that takes an existing translation and runs a configurable LLM pass to fix grammar, spelling, and awkward phrasing — without changing meaning, terminology, or character names. Outputs a corrected EPUB (or plain text) with the original's fonts, styling, and structure intact, plus a full SQLite audit trail of every change.

**500 chapters of a million-word novel: ~$0.65 and ~15 minutes.**

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/your-username/tlmend
cd tlmend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 2. Set your API key (DeepSeek recommended — cheapest)
export DEEPSEEK_API_KEY=sk-...

# 3. Create a project
mkdir -p projects/my-novel/source
cp your-novel.epub projects/my-novel/source/

# 4. Create projects/my-novel/config.toml  (see template below)

# 5. Run
.venv/bin/tlmend run projects/my-novel --range 2-501 --concurrency 64
```

Output lands at `projects/my-novel/output/output.epub`.

---

## Config template

Create `config.toml` inside your project directory:

```toml
[project]
name         = "My Novel"
source_format = "epub"     # epub | txt
output_format = "epub"     # epub | txt

[pipeline]
mode        = "edit"       # edit | review  (see Modes below)
policy      = "report"     # trust | report | conservative  (edit mode only)
concurrency = 64           # parallel LLM calls — higher = faster, same cost
cost_cap_usd = 5.0         # hard abort if accumulated cost exceeds this

[editor]
provider = "deepseek"
model    = "deepseek-v4-flash"

[reviewer]                 # only used in review mode
provider = "deepseek"
model    = "deepseek-v4-flash"

[glossary]
path = "glossary.json"     # optional — list of proper nouns to never alter
```

---

## Providers

Set the matching environment variable before running:

| Provider | Env var | Recommended model | Cost / 500 ch |
|---|---|---|---|
| **DeepSeek** *(recommended)* | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` | ~$0.65 |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` | ~$1.14 |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` | ~$7 |

Change `[editor] provider` and `model` in `config.toml` to switch. No other changes needed.

---

## Modes

### `edit` (default)
Single LLM pass. Every change is classified as mechanical or substantive, then resolved by **policy**:

| Policy | What happens to substantive changes |
|---|---|
| `trust` | Apply everything automatically |
| `report` | Apply but log for human review |
| `conservative` | Keep the original — only apply mechanical fixes |

### `review`
Two-pass. Mechanical changes are applied automatically. Substantive changes go to a second reviewer LLM which accepts, rejects, or modifies each one. Slower and ~2× the cost.

---

## Change classification

Every diff hunk is classified before any decision is made:

- **mechanical** — punctuation, spacing, capitalisation, obvious typos. Applied automatically in both modes.
- **substantive** — rewording, phrase changes, anything that alters meaning. Subject to policy (edit mode) or reviewer adjudication (review mode).

The stats shown after each chapter (`4mech 1sub`) tell you how many of each were found.

---

## CLI reference

```
tlmend run <project> [options]

Arguments:
  project         Path to project directory (must contain config.toml)

Options:
  --range 1-50    Process only chapters 1–50 (1-indexed, inclusive).
                  Useful for testing before committing to a full run.
                  The first item in an EPUB spine is index 1.
  --concurrency   Parallel LLM calls. Overrides config.toml.
                  Higher = faster wall time, identical cost.
                  64 is a safe default for DeepSeek.
  -j              Short alias for --concurrency
  --mode          edit or review. Overrides config.
  --policy        trust, report, or conservative. Overrides config.
  --dry-run       Count source files and exit — no LLM calls.
```

### Resume

If a run is interrupted, just re-run the same command. Already-assembled chapters are skipped automatically. No flags needed.

---

## EPUB notes

- The output EPUB is the input EPUB with paragraph text replaced — all original CSS, fonts, images, cover, table of contents, and metadata are preserved exactly.
- Front matter (cover, title page, TOC) and back matter (notes) pass through unchanged.
- Chapter spine indices start at 1. Use `--range 2-501` to skip a front-matter page at index 1 and process 500 chapters.

---

## Glossary

Create `glossary.json` in your project directory to protect proper nouns:

```json
["Fang Yuan", "Spring Autumn Cicada", "Gu Yue clan", "Reverend Insanity"]
```

Any term present in the original chapter text must still appear in the corrected output — validation rejects the chapter if one goes missing.

---

## Project layout

```
projects/my-novel/
  config.toml          # settings
  glossary.json        # optional protected terms
  source/              # gitignored — put your .epub or .txt here
  output/              # generated — output.epub / output.txt
  run.sqlite           # audit trail — every change, decision, and cost logged
```

---

## Development

```bash
.venv/bin/pytest              # 70 tests, ~1s
.venv/bin/ruff check .
.venv/bin/mypy tlmend
```
