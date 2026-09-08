"""Persistent shortlist: saved niches, tracked keywords and past runs."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_niches (
    id TEXT PRIMARY KEY,
    keyword TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    store TEXT NOT NULL,
    score REAL DEFAULT 0,
    note TEXT DEFAULT '',
    payload TEXT NOT NULL,
    created REAL NOT NULL,
    UNIQUE (keyword, marketplace, store)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    seed TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    store TEXT NOT NULL,
    niches INTEGER DEFAULT 0,
    payload TEXT NOT NULL,
    created REAL NOT NULL
);
"""


class Storage:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with _LOCK:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------- shortlist
    def save_niche(self, niche: dict, note: str = "") -> dict:
        row_id = uuid.uuid4().hex[:12]
        with _LOCK:
            self._conn.execute(
                "INSERT INTO saved_niches (id, keyword, marketplace, store, score, note, payload, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(keyword, marketplace, store) DO UPDATE SET"
                " score=excluded.score, note=excluded.note, payload=excluded.payload,"
                " created=excluded.created",
                (row_id, niche.get("keyword", ""), niche.get("marketplace", "us"),
                 niche.get("store", "print"), float(niche.get("opportunity_score") or 0),
                 note, json.dumps(niche), time.time()),
            )
            self._conn.commit()
        return {"id": row_id, "keyword": niche.get("keyword", "")}

    def list_niches(self) -> list[dict]:
        with _LOCK:
            rows = self._conn.execute(
                "SELECT * FROM saved_niches ORDER BY score DESC, created DESC").fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["payload"])
            payload["_saved_id"] = row["id"]
            payload["_note"] = row["note"]
            payload["_saved_at"] = row["created"]
            out.append(payload)
        return out

    def delete_niche(self, keyword: str, marketplace: str, store: str) -> bool:
        with _LOCK:
            cur = self._conn.execute(
                "DELETE FROM saved_niches WHERE keyword=? AND marketplace=? AND store=?",
                (keyword, marketplace, store))
            self._conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------ runs
    def save_run(self, run: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        with _LOCK:
            self._conn.execute(
                "INSERT INTO runs (id, seed, marketplace, store, niches, payload, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, run.get("seed", ""), run.get("marketplace", "us"),
                 run.get("store", "print"), len(run.get("niches", [])),
                 json.dumps(run), time.time()),
            )
            self._conn.execute(
                "DELETE FROM runs WHERE id NOT IN"
                " (SELECT id FROM runs ORDER BY created DESC LIMIT 50)")
            self._conn.commit()
        return run_id

    def list_runs(self, limit: int = 25) -> list[dict]:
        with _LOCK:
            rows = self._conn.execute(
                "SELECT id, seed, marketplace, store, niches, created FROM runs"
                " ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with _LOCK:
            row = self._conn.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None
