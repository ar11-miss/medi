"""SQLite storage for cases (one illness episode) and their daily check-ins."""
import json
import sqlite3
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    start_day     TEXT NOT NULL,          -- ISO date of day 1
    language      TEXT NOT NULL DEFAULT 'en',
    profile       TEXT NOT NULL DEFAULT '{}',
    condition     TEXT,
    level         TEXT,                   -- current severity level
    specialty     TEXT,
    first_score   INTEGER,                -- symptom score (1-10) on day 1
    xp            INTEGER NOT NULL DEFAULT 0,
    badges        TEXT NOT NULL DEFAULT '[]',
    quests        TEXT NOT NULL DEFAULT '[]',   -- quests for the next check-in
    quest_counts  TEXT NOT NULL DEFAULT '{}',   -- how often each kind was done
    status        TEXT NOT NULL DEFAULT 'active'  -- active | recovered
);
CREATE TABLE IF NOT EXISTS checkins (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id      INTEGER NOT NULL REFERENCES cases(id),
    day          TEXT NOT NULL,           -- ISO date
    feeling      TEXT NOT NULL,           -- better | same | worse
    score        INTEGER NOT NULL,        -- 1-10
    note         TEXT,
    quests_done  TEXT NOT NULL DEFAULT '[]',
    xp_gained    INTEGER NOT NULL DEFAULT 0,
    level        TEXT,                    -- severity level after this check-in
    message      TEXT
);
"""

_JSON_FIELDS = ("profile", "badges", "quests", "quest_counts", "quests_done", "last_result")


def _decode(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in _JSON_FIELDS:
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    return d


def _encode(v):
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


class DB:
    def __init__(self, path: str = "mediaid.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # newer column, added to databases made by older versions
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(cases)")}
        if "last_result" not in cols:
            self.conn.execute("ALTER TABLE cases ADD COLUMN last_result TEXT NOT NULL DEFAULT '{}'")
            self.conn.commit()

    def create_case(self, *, start_day: date, language: str, profile: dict, condition: str | None,
                    level: str, specialty: str | None, first_score: int, quests: list) -> int:
        cur = self.conn.execute(
            "INSERT INTO cases (start_day, language, profile, condition, level, specialty, first_score, quests) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (start_day.isoformat(), language, _encode(profile), condition, level, specialty,
             first_score, _encode(quests)))
        self.conn.commit()
        return cur.lastrowid

    def get_case(self, case_id: int) -> dict | None:
        return _decode(self.conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())

    def latest_case(self) -> dict | None:
        return _decode(self.conn.execute("SELECT * FROM cases ORDER BY id DESC LIMIT 1").fetchone())

    def update_case(self, case_id: int, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE cases SET {cols} WHERE id = ?",
                          [_encode(v) for v in fields.values()] + [case_id])
        self.conn.commit()

    def add_checkin(self, case_id: int, **fields) -> None:
        fields["case_id"] = case_id
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self.conn.execute(f"INSERT INTO checkins ({cols}) VALUES ({marks})",
                          [_encode(v) for v in fields.values()])
        self.conn.commit()

    def checkins(self, case_id: int) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM checkins WHERE case_id = ? ORDER BY day, id", (case_id,))
        return [_decode(r) for r in rows]
