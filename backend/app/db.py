from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    work_date TEXT NOT NULL,
    building TEXT NOT NULL,
    floor TEXT NOT NULL,
    address_code TEXT NOT NULL,
    material TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    storage_root TEXT NOT NULL,
    folder_path TEXT NOT NULL UNIQUE,
    photo_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    stored_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_work_date
ON cases(work_date DESC);

CREATE INDEX IF NOT EXISTS idx_cases_building_address
ON cases(building, address_code);

CREATE INDEX IF NOT EXISTS idx_cases_material
ON cases(material);

CREATE INDEX IF NOT EXISTS idx_photos_sha256
ON photos(sha256);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_options (
    id INTEGER PRIMARY KEY,
    option_type TEXT NOT NULL CHECK(option_type IN ('material', 'issue')),
    value TEXT NOT NULL COLLATE NOCASE,
    created_at TEXT NOT NULL,
    UNIQUE(option_type, value)
);

CREATE INDEX IF NOT EXISTS idx_custom_options_type
ON custom_options(option_type, id);
"""


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(database_path)) as connection, connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
        case_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(cases)").fetchall()
        }
        if "storage_root" not in case_columns:
            connection.execute(
                "ALTER TABLE cases ADD COLUMN storage_root TEXT NOT NULL DEFAULT ''"
            )
        connection.execute("PRAGMA optimize")


def get_setting(database_path: Path, key: str, default: str = "") -> str:
    with connect(database_path) as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row is not None else default


def set_setting(database_path: Path, key: str, value: str) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
