"""SQLite schema. The ledger file is the single source of truth."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import ROOT

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- One row per spend message. bucket NULL = Unsorted (waiting for an answer);
-- paid_by NULL = payer unknown (waiting for an answer).
CREATE TABLE IF NOT EXISTS entries (
    id              INTEGER PRIMARY KEY,
    created_at      TEXT NOT NULL,
    spent_on        TEXT NOT NULL,          -- YYYY-MM-DD, local time
    place           TEXT NOT NULL,          -- where / what, as shown in the table ("Sushi-Mentai")
    item            TEXT,                   -- optional detail ("lunch")
    category        TEXT,                   -- descriptive label (Food, Sport, ...)
    bucket          TEXT,                   -- budget bucket key, NULL = Unsorted
    bucket_options  TEXT,                   -- JSON list the bot offered when unsure
    total_sen       INTEGER NOT NULL CHECK (total_sen > 0),
    paid_by         TEXT,                   -- person key, NULL = unknown
    sender          TEXT NOT NULL,          -- person key of whoever sent the message
    raw_text        TEXT,
    chat_id         TEXT,
    msg_id          TEXT,
    question_msg_id TEXT,                   -- the bot's clarifying question, to match replies
    deleted_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS entries_msg ON entries(chat_id, msg_id) WHERE msg_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS entries_spent_on ON entries(spent_on);

-- Whose spending it is. Shares always add up to the entry total.
CREATE TABLE IF NOT EXISTS shares (
    entry_id   INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    person     TEXT NOT NULL,
    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 0),
    PRIMARY KEY (entry_id, person)
);

-- Money moved between the two of you to clear the balance. Never touches budgets.
CREATE TABLE IF NOT EXISTS settlements (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL,
    settled_on  TEXT NOT NULL,
    from_person TEXT NOT NULL,
    to_person   TEXT NOT NULL,
    amount_sen  INTEGER NOT NULL CHECK (amount_sen > 0),
    raw_text    TEXT,
    chat_id     TEXT,
    msg_id      TEXT,
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS settlements_msg ON settlements(chat_id, msg_id) WHERE msg_id IS NOT NULL;

-- Per-month plan, copied forward from the previous month (or config) on first use.
CREATE TABLE IF NOT EXISTS plans (
    month      TEXT NOT NULL,
    person     TEXT NOT NULL,
    bucket     TEXT NOT NULL,
    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 0),
    PRIMARY KEY (month, person, bucket)
);

-- Fixed bills (house, car): Paid / Due per month per person.
CREATE TABLE IF NOT EXISTS fixed_payments (
    month      TEXT NOT NULL,
    person     TEXT NOT NULL,
    bucket     TEXT NOT NULL,
    amount_sen INTEGER NOT NULL,
    paid_at    TEXT,                        -- NULL = Due
    auto       INTEGER NOT NULL DEFAULT 0,  -- 1 = marked paid automatically
    PRIMARY KEY (month, person, bucket)
);

-- Learned places: "sushimentai" -> Sushi-Mentai / Food / daily.
CREATE TABLE IF NOT EXISTS places (
    key      TEXT PRIMARY KEY,              -- normalised name
    display  TEXT NOT NULL,
    bucket   TEXT,                          -- bucket key or 'daily'
    category TEXT,
    uses     INTEGER NOT NULL DEFAULT 0
);
"""


def default_path() -> Path:
    return Path(os.environ.get("DUIT_DB", ROOT / "data" / "duit.db"))


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    path = default_path() if path is None else path
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # autocommit (transactions are explicit); MCP runs sync tools in worker threads, callers serialise access
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")  # bot and dashboard share the file
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    return conn
