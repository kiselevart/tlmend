"""SQLite-backed audit store via aiosqlite."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from tlmend.models import CompletionResult, Hunk, Resolution

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project        TEXT NOT NULL,
    mode           TEXT NOT NULL,
    policy         TEXT,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    prompt_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    chapter_id  TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    UNIQUE(run_id, chapter_id)
);

CREATE TABLE IF NOT EXISTS edits (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_row_id    INTEGER NOT NULL REFERENCES chapters(id),
    attempt           INTEGER NOT NULL DEFAULT 1,
    original_text     TEXT NOT NULL,
    proposed_text     TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd          REAL NOT NULL,
    model             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_row_id  INTEGER NOT NULL REFERENCES chapters(id),
    paragraph_index INTEGER NOT NULL,
    original_text   TEXT NOT NULL,
    proposed_text   TEXT NOT NULL,
    classification  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolutions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    hunk_id    INTEGER NOT NULL REFERENCES hunks(id),
    decision   TEXT NOT NULL,
    final_text TEXT NOT NULL,
    reason     TEXT
);

CREATE TABLE IF NOT EXISTS cost_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER NOT NULL REFERENCES runs(id),
    stage             TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd          REAL NOT NULL,
    recorded_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> "Store":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Store is not open")
        return self._db

    # --- runs ---

    async def create_run(
        self, project: str, mode: str, policy: str | None, prompt_version: str, started_at: str
    ) -> int:
        cur = await self._conn.execute(
            "INSERT INTO runs (project, mode, policy, started_at, prompt_version) VALUES (?,?,?,?,?)",
            (project, mode, policy, started_at, prompt_version),
        )
        await self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def find_or_create_run(
        self, project: str, mode: str, policy: str | None, prompt_version: str, started_at: str
    ) -> int:
        """Reuse the latest incomplete run for *project*, or create a new one."""
        row = await (await self._conn.execute(
            "SELECT id FROM runs WHERE project=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
            (project,),
        )).fetchone()
        if row is not None:
            return int(row[0])
        return await self.create_run(project, mode, policy, prompt_version, started_at)

    async def finish_run(self, run_id: int) -> None:
        await self._conn.execute(
            "UPDATE runs SET ended_at=datetime('now') WHERE id=?", (run_id,)
        )
        await self._conn.commit()

    # --- chapters ---

    async def get_or_create_chapter(
        self, run_id: int, chapter_id: str, title: str
    ) -> tuple[int, str]:
        """Return (chapter_row_id, current_status). Creates with PENDING if missing."""
        row = await (await self._conn.execute(
            "SELECT id, status FROM chapters WHERE run_id=? AND chapter_id=?",
            (run_id, chapter_id),
        )).fetchone()
        if row is not None:
            return int(row[0]), str(row[1])

        cur = await self._conn.execute(
            "INSERT INTO chapters (run_id, chapter_id, title, status) VALUES (?,?,?,?)",
            (run_id, chapter_id, title, "pending"),
        )
        await self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid, "pending"

    async def set_chapter_status(self, chapter_row_id: int, status: str) -> None:
        await self._conn.execute(
            "UPDATE chapters SET status=? WHERE id=?", (status, chapter_row_id)
        )
        await self._conn.commit()

    # --- edits ---

    async def write_edit(
        self,
        chapter_row_id: int,
        original: str,
        proposed: str,
        result: CompletionResult,
        attempt: int,
    ) -> int:
        cur = await self._conn.execute(
            "INSERT INTO edits (chapter_row_id, attempt, original_text, proposed_text,"
            " prompt_tokens, completion_tokens, cost_usd, model) VALUES (?,?,?,?,?,?,?,?)",
            (chapter_row_id, attempt, original, proposed,
             result.prompt_tokens, result.completion_tokens, result.cost_usd, result.model),
        )
        await self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    # --- hunks ---

    async def write_hunk(self, chapter_row_id: int, hunk: Hunk) -> int:
        cur = await self._conn.execute(
            "INSERT INTO hunks (chapter_row_id, paragraph_index, original_text, proposed_text, classification)"
            " VALUES (?,?,?,?,?)",
            (chapter_row_id, hunk.index, hunk.original, hunk.proposed, hunk.classification),
        )
        await self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    # --- resolutions ---

    async def write_resolution(self, hunk_id: int, resolution: Resolution) -> int:
        cur = await self._conn.execute(
            "INSERT INTO resolutions (hunk_id, decision, final_text, reason) VALUES (?,?,?,?)",
            (hunk_id, resolution.decision, resolution.final_text, resolution.reason),
        )
        await self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    # --- cost ---

    async def log_cost(
        self, run_id: int, stage: str, model: str,
        prompt_tokens: int, completion_tokens: int, cost_usd: float,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO cost_log (run_id, stage, model, prompt_tokens, completion_tokens, cost_usd)"
            " VALUES (?,?,?,?,?,?)",
            (run_id, stage, model, prompt_tokens, completion_tokens, cost_usd),
        )
        await self._conn.commit()

    async def total_cost(self, run_id: int) -> float:
        row = await (await self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE run_id=?", (run_id,)
        )).fetchone()
        return float(row[0])
