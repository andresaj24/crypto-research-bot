"""SQLite ledger — records every LLM call and pipeline run for auditing.

Design choices that differ from a naive tracker:
  * Separate ``calls`` and ``missions`` tables (a mission = one full
    pipeline execution for a single target).
  * ``daily_heatmap`` returns per-day + per-tag token totals for a
    compact visual overview.
  * WAL mode + thread lock for safe concurrent writes from the async
    monitor loop.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterator, Optional


_DDL = """
CREATE TABLE IF NOT EXISTS calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    tag         TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    prompt_tok  INTEGER NOT NULL,
    gen_tok     INTEGER NOT NULL,
    total_tok   INTEGER NOT NULL,
    ref         TEXT,
    ms          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_calls_ts  ON calls(ts);
CREATE INDEX IF NOT EXISTS ix_calls_tag ON calls(tag);

CREATE TABLE IF NOT EXISTS missions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    ref         TEXT    NOT NULL,
    network     TEXT,
    contract    TEXT,
    ticker      TEXT,
    threat      INTEGER,
    signal      TEXT,
    tokens_used INTEGER NOT NULL,
    ms          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_missions_ts ON missions(ts);
"""


class Ledger:
    """Thread-safe SQLite ledger for LLM calls and pipeline missions."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._mu = threading.Lock()
        with self._conn() as c:
            c.executescript(_DDL)
            c.execute("PRAGMA journal_mode=WAL;")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── writes ───────────────────────────────────────────────────

    def log_call(
        self,
        *,
        tag: str,
        model: str,
        prompt_tok: int,
        gen_tok: int,
        ref: Optional[str] = None,
        ms: int = 0,
    ) -> None:
        total = prompt_tok + gen_tok
        ts = datetime.now(timezone.utc).isoformat()
        with self._mu, self._conn() as c:
            c.execute(
                "INSERT INTO calls (ts,tag,model,prompt_tok,gen_tok,total_tok,ref,ms) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ts, tag, model, prompt_tok, gen_tok, total, ref, ms),
            )

    def log_mission(
        self,
        *,
        ref: str,
        network: Optional[str],
        contract: Optional[str],
        ticker: Optional[str],
        threat: Optional[int],
        signal: Optional[str],
        tokens_used: int,
        ms: int,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._mu, self._conn() as c:
            c.execute(
                "INSERT INTO missions (ts,ref,network,contract,ticker,threat,signal,tokens_used,ms) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, ref, network, contract, ticker, threat, signal, tokens_used, ms),
            )

    # ── reads ────────────────────────────────────────────────────

    def total_tokens(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COALESCE(SUM(total_tok),0) FROM calls").fetchone()[0])

    def tokens_today(self) -> int:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(total_tok),0) FROM calls WHERE ts LIKE ?",
                (f"{day}%",),
            ).fetchone()
            return int(row[0])

    def by_tag(self) -> list[tuple[str, int, int]]:
        """(tag, num_calls, total_tokens) sorted by tokens desc."""
        with self._conn() as c:
            return [
                (r[0], int(r[1]), int(r[2]))
                for r in c.execute(
                    "SELECT tag, COUNT(*), COALESCE(SUM(total_tok),0) "
                    "FROM calls GROUP BY tag ORDER BY 3 DESC"
                ).fetchall()
            ]

    def recent_missions(self, n: int = 20) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT ts,ref,network,ticker,threat,signal,tokens_used,ms "
                "FROM missions ORDER BY id DESC LIMIT ?",
                (n,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def daily_heatmap(self, days: int = 7) -> list[tuple[str, int, int]]:
        """(date, num_calls, total_tokens) for the last N days."""
        with self._conn() as c:
            return [
                (r[0], int(r[1]), int(r[2]))
                for r in c.execute(
                    "SELECT substr(ts,1,10) AS d, COUNT(*), COALESCE(SUM(total_tok),0) "
                    "FROM calls GROUP BY d ORDER BY d DESC LIMIT ?",
                    (days,),
                ).fetchall()
            ]

    def mission_count(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM missions").fetchone()[0])
