"""Tiny SQLite cache so repeated research never re-hits Amazon."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

_LOCK = threading.Lock()


class Cache:
    def __init__(self, path: str, ttl: int = 43200) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.ttl = ttl
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str, ttl: int | None = None):
        ttl = self.ttl if ttl is None else ttl
        with _LOCK:
            row = self._conn.execute(
                "SELECT value, created FROM entries WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        value, created = row
        if ttl >= 0 and time.time() - created > ttl:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value) -> None:
        with _LOCK:
            self._conn.execute(
                "INSERT OR REPLACE INTO entries (key, value, created) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time()),
            )
            self._conn.commit()

    def purge(self, older_than: float | None = None) -> int:
        cutoff = time.time() - (older_than if older_than is not None else self.ttl)
        with _LOCK:
            cur = self._conn.execute("DELETE FROM entries WHERE created < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def clear(self) -> None:
        with _LOCK:
            self._conn.execute("DELETE FROM entries")
            self._conn.commit()

    def stats(self) -> dict:
        with _LOCK:
            n = self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        return {"entries": n, "path": self.path, "ttl": self.ttl}
