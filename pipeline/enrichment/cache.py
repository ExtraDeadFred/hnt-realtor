"""SQLite key-value cache with TTLs for enrichment data sources."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

DAY = 86400
TTL = {
    "tract_geo": 365 * DAY,   # geocode results are stable
    "acs": 180 * DAY,         # annual releases
    "hud_points": 90 * DAY,   # quarterly-ish updates
    "crime": 30 * DAY,        # monthly refresh is plenty
}


class Cache:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS cache (
                 namespace TEXT NOT NULL,
                 key       TEXT NOT NULL,
                 value     TEXT NOT NULL,
                 stored_at REAL NOT NULL,
                 PRIMARY KEY (namespace, key))""")

    def get(self, namespace: str, key: str) -> Any | None:
        row = self.conn.execute(
            "SELECT value, stored_at FROM cache WHERE namespace=? AND key=?",
            (namespace, key)).fetchone()
        if row is None:
            return None
        value, stored_at = row
        if time.time() - stored_at > TTL.get(namespace, 30 * DAY):
            return None
        return json.loads(value)

    def set(self, namespace: str, key: str, value: Any) -> None:
        self.conn.execute(
            """INSERT INTO cache (namespace, key, value, stored_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(namespace, key) DO UPDATE SET
                 value=excluded.value, stored_at=excluded.stored_at""",
            (namespace, key, json.dumps(value), time.time()))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
