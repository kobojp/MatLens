from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

from backend.app.db import connect, initialize


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def user_data_dir() -> Path:
    override = os.getenv("MATLENS_DESKTOP_DATA_DIR")
    if override:
        return Path(override).resolve()
    return Path(os.environ["LOCALAPPDATA"]) / "MatLens"


def migrate_legacy(source: Path, destination: Path) -> Path | None:
    """Copy a consistent SQLite snapshot; never alter the source or copy/move photos."""
    if destination.exists() or not source.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    backups = destination.parent / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backups / f"legacy-{stamp}-{uuid.uuid4().hex[:8]}.db"
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(backup)) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("舊版資料庫檢查失敗，已停止匯入。")
            tables = {row[0] for row in dst.execute("SELECT name FROM sqlite_master")}
            if not {"cases", "photos"}.issubset(tables):
                raise RuntimeError("選取的檔案不是 MatLens 案件資料庫。")
    staged = destination.with_name(f"migration-{uuid.uuid4().hex}.db")
    with closing(sqlite3.connect(backup)) as src, closing(sqlite3.connect(staged)) as dst:
        src.backup(dst)
    initialize(staged)
    legacy_photos = str((source.parent / "photos").resolve())
    with closing(connect(staged)) as db, db:
        db.execute(
            "UPDATE cases SET storage_root = ? WHERE storage_root = '' OR storage_root IS NULL",
            (legacy_photos,),
        )
        db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('storage_root', ?)",
            (legacy_photos,),
        )
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('legacy_source', ?)",
                   (str(source.resolve()),))
    # Close all handles and checkpoint before publishing the new database.
    with closing(sqlite3.connect(staged)) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("PRAGMA journal_mode = DELETE")
    staged.rename(destination)
    return backup
