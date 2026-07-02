"""
Rolling hours-long history: a small SQLite log written by the `--collect`
background loop (see cli.py) and read back as max/avg/now over five time
windows by the dashboard and the HTTP server's /history endpoint.

One row per (timestamp, sensor, JSON blob of that sensor's derive() output)
-- simpler than a normalized schema, and the data volume is tiny (a few
sensors sampled every ~10 s for a couple of days is a few thousand rows).
"""

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path.home() / "Library/Application Support/macpower/history.sqlite3"

RETENTION_SECONDS = 48 * 3600  # comfortably more than the longest window below

WINDOWS = [("10m", 600), ("30m", 1800), ("1h", 3600), ("2h", 7200), ("4h", 14400)]


def connect(path=None) -> sqlite3.Connection:
    """Open (creating if needed) the history database. Pass ":memory:" for tests."""
    path = DB_PATH if path is None else path
    if path != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS readings (ts REAL, sensor TEXT, data TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_sensor_ts ON readings (sensor, ts)")
    conn.commit()
    return conn


def record(conn: sqlite3.Connection, ts: float, sensor: str, derived: dict) -> None:
    conn.execute("INSERT INTO readings VALUES (?, ?, ?)", (ts, sensor, json.dumps(derived)))
    conn.execute("DELETE FROM readings WHERE ts < ?", (ts - RETENTION_SECONDS,))
    conn.commit()


def series(conn: sqlite3.Connection, sensor: str, key: str, since: float) -> list:
    """[(ts, value)] for one numeric field, oldest first."""
    rows = conn.execute(
        "SELECT ts, data FROM readings WHERE sensor = ? AND ts >= ? ORDER BY ts",
        (sensor, since),
    ).fetchall()
    out = []
    for ts, blob in rows:
        value = json.loads(blob).get(key)
        if isinstance(value, (int, float)):
            out.append((ts, value))
    return out


def window_stats(conn: sqlite3.Connection, sensor: str, key: str, now: float = None) -> dict:
    """{'10m': {'max':, 'avg':, 'now':}, '30m': {...}, ..., '4h': {...}}"""
    now = time.time() if now is None else now
    points = series(conn, sensor, key, now - WINDOWS[-1][1])

    out = {}
    for label, span in WINDOWS:
        vals = [v for ts, v in points if ts >= now - span]
        if vals:
            out[label] = {"max": max(vals), "avg": round(sum(vals) / len(vals), 2), "now": vals[-1]}
        else:
            out[label] = {"max": None, "avg": None, "now": None}
    return out
