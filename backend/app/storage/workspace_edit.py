"""Copy-on-write photo changes for the existing-case workspace.

Original case files remain in a hidden history directory. A durable journal and
SQLite revision distinguish interrupted exchanges, including unchanged folder names.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from fastapi import UploadFile

from ..db import connect
from ..schemas import CaseEdit
from .cases import _save_upload
from .editing import (
    EditConflict,
    _checked_folder,
    _files,
    _plan,
    _snapshot,
    _write_case,
    edit_detail,
    update_case,
)
from .errors import DuplicatePhotoError, StorageError
from .naming import stored_names
from .records import insert_photo_row


def photo_change_plan(connection, case_id: str, change: CaseEdit) -> dict:
    rows = connection.execute(
        "SELECT * FROM photos WHERE case_id=? ORDER BY sequence", (case_id,)
    ).fetchall()
    if change.photos is None:
        return {"photos_changed": False, "added": 0, "removed": 0}
    existing = {row["id"]: row for row in rows}
    retained = [photo.photo_id for photo in change.photos if photo.photo_id is not None]
    uploads = [photo.upload_index for photo in change.photos if photo.upload_index is not None]
    if len(set(retained)) != len(retained) or not set(retained) <= existing.keys():
        raise StorageError("照片不屬於此案件或重複選取，請重新載入")
    if sorted(uploads) != list(range(len(uploads))):
        raise StorageError("新增照片的索引不正確")
    original_sequence = bool(rows) and all(re.match(r"^\d+_", row["stored_name"]) for row in rows)
    before = [(row["id"], row["role"]) for row in rows]
    after = [(photo.photo_id, photo.role) for photo in change.photos]
    return {
        "photos_changed": before != after or original_sequence != change.name_with_sequence,
        "added": len(uploads),
        "removed": len(existing.keys() - set(retained)),
    }


def _photo_journal(
    database: Path,
    case_id: str,
    root: Path,
    old: Path,
    new: Path,
    archive: Path,
    stage: Path,
    revision: str,
) -> Path:
    directory = database.parent / "case-edits"
    directory.mkdir(exist_ok=True)
    path = directory / (revision + ".json")
    with closing(connect(database)) as connection:
        old_revision = connection.execute(
            "SELECT edit_revision FROM cases WHERE id=?", (case_id,)
        ).fetchone()[0]
    payload = {
        "kind": "photos",
        "case_id": case_id,
        "root": str(root),
        "old": str(old),
        "new": str(new),
        "archive": str(archive),
        "stage": str(stage),
        "revision": revision,
        "old_revision": old_revision,
        "before_files": _files(old),
        "after_files": _files(stage),
    }
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    return path


def recover_photo_edit(connection, path: Path, job: dict) -> None:
    root = Path(job["root"])
    paths = {
        key: _checked_folder(root, Path(job[key]).relative_to(root).as_posix(), must_exist=False)
        for key in ["old", "new", "archive", "stage"]
    }
    old, new, archive, stage = (paths[key] for key in ["old", "new", "archive", "stage"])
    if archive.parent != root / ".matlens-history" or stage.parent != root / ".staging":
        raise StorageError("照片恢復路徑不正確，請保留更正紀錄")
    row = connection.execute(
        "SELECT storage_root,folder_path,edit_revision FROM cases WHERE id=?", (job["case_id"],)
    ).fetchone()
    if row is None or Path(row["storage_root"] or job["root"]) != root:
        raise StorageError("照片更正恢復資訊不一致")
    if row["edit_revision"] == job["revision"]:
        if root / row["folder_path"] != new or not new.is_dir():
            raise StorageError("已儲存案件的照片路徑不確定，請保留紀錄")
    elif row["edit_revision"] == job["old_revision"] and root / row["folder_path"] == old:
        if archive.exists():
            if _files(archive) != job["before_files"]:
                raise StorageError("原照片備份內容已變更，停止自動恢復")
            if new.exists():
                if (
                    (old != new and old.exists())
                    or stage.exists()
                    or _files(new) != job["after_files"]
                ):
                    raise StorageError("照片恢復遇到多個路徑或外部變更，停止猜測")
                new.rename(stage)
            if old.exists():
                raise StorageError("原照片路徑已被占用，不能覆蓋")
            archive.rename(old)
        elif not old.is_dir() or _files(old) != job["before_files"]:
            raise StorageError("原案件內容不確定，請保留照片更正紀錄")
    else:
        raise StorageError("案件已被其他作業更正，不能自動回復")
    path.unlink()


def _prepare_photos(
    connection, case_id: str, change: CaseEdit, old: Path, stage: Path, uploaded: list[dict]
) -> list[dict]:
    existing = {
        row["id"]: dict(row)
        for row in connection.execute("SELECT * FROM photos WHERE case_id=?", (case_id,))
    }
    names = {row["stored_name"] for row in existing.values()}
    for file in old.rglob("*"):
        if file.is_file() and file.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            if file.parent != old or file.name not in names:
                raise EditConflict("資料夾含未登錄照片，請先掃描再重新載入案件")
    # Preserve unrelated files without overwriting any staged image.
    for file in old.rglob("*"):
        relative = file.relative_to(old)
        if file.parent == old and file.name in names:
            continue
        target = stage / relative
        if file.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif file.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
    items = []
    for photo in change.photos or []:
        if photo.photo_id is not None:
            item = dict(existing[photo.photo_id])
            item["source"] = old / item["stored_name"]
            with item["source"].open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != item["sha256"]:
                    raise EditConflict("照片內容與紀錄不一致，請先掃描再編輯")
        else:
            item = dict(uploaded[photo.upload_index])
        item["role"] = photo.role
        items.append(item)
    hashes = [item["sha256"] for item in items]
    uploaded_ids = {item["id"] for item in uploaded}
    added_hashes = [item["sha256"] for item in items if item["id"] in uploaded_ids]
    if any(hashes.count(digest) > 1 for digest in added_hashes):
        raise StorageError("本次新增的照片重複，請移除重複項目")
    if added_hashes:
        placeholders = ",".join("?" for _ in added_hashes)
        duplicates = connection.execute(
            "SELECT original_name,case_id FROM photos WHERE case_id!=? "
            f"AND sha256 IN ({placeholders})",
            [case_id, *added_hashes],
        ).fetchall()
        if duplicates:
            raise DuplicatePhotoError([dict(row) for row in duplicates])
    generated = stored_names(
        [item["role"] for item in items],
        [Path(item["source"]).suffix for item in items],
        with_sequence=change.name_with_sequence,
    )
    for item, name in zip(items, generated, strict=True):
        target = stage / name
        if target.exists():
            raise StorageError("照片新名稱與資料夾既有檔案衝突，不會覆蓋")
        shutil.copy2(item["source"], target)
        item["stored_name"] = name
    return items


async def save_workspace(
    database: Path, case_id: str, change: CaseEdit, fallback_root: Path, uploads: list[UploadFile]
) -> dict:
    with closing(connect(database)) as check:
        plan = photo_change_plan(check, case_id, change)
    if len(uploads) != plan["added"]:
        raise StorageError("新增照片與上傳檔案數量不一致")
    if not plan["photos_changed"]:
        result = update_case(database, case_id, change, fallback_root)
        return {**result, **edit_detail(database, case_id, fallback_root)}
    journal = None
    with closing(connect(database)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("SAVEPOINT workspace_save")
        try:
            case, root, old, new, naming = _plan(connection, case_id, change, fallback_root)
            if not case["app_managed"] and not change.confirm_managed:
                raise EditConflict("請確認這是整理後的案件資料夾，非原始來源照片目錄")
            # Validate all generated destinations under the original storage root before moves.
            revision = uuid.uuid4().hex
            stage = _checked_folder(root, ".staging/" + revision, must_exist=False)
            archive = _checked_folder(root, ".matlens-history/" + revision, must_exist=False)
            stage.mkdir(parents=True)
            archive.parent.mkdir(exist_ok=True)
            incoming = []
            for index, upload in enumerate(uploads):
                temporary = stage / f".upload-{index}.bin"
                digest, size, width, height, extension = await _save_upload(upload, temporary)
                source = temporary.with_suffix(extension)
                temporary.rename(source)
                incoming.append(
                    dict(
                        id=str(uuid.uuid4()),
                        source=source,
                        sha256=digest,
                        size_bytes=size,
                        width=width,
                        height=height,
                        original_name=upload.filename or "photo",
                    )
                )
            items = _prepare_photos(connection, case_id, change, old, stage, incoming)
            for item in incoming:
                item["source"].unlink()  # Exact temporary files owned by this job.
            backups = database.parent / "backups"
            backups.mkdir(exist_ok=True)
            with (
                closing(connect(database)) as source,
                closing(
                    sqlite3.connect(backups / ("before-case-edit-" + revision + ".db"))
                ) as backup,
            ):
                source.backup(backup)
            if _snapshot(connection, case_id, fallback_root)[3] != change.token:
                raise EditConflict("準備期間案件內容已變更，請重新載入")
            journal = _photo_journal(database, case_id, root, old, new, archive, stage, revision)
            if new != old and new.exists():
                raise EditConflict("新資料夾已存在，不能覆蓋")
            old.rename(archive)
            stage.rename(new)
            _write_case(connection, case_id, change, new.relative_to(root).as_posix(), naming)
            connection.execute("DELETE FROM photos WHERE case_id=?", (case_id,))
            for sequence, item in enumerate(items, start=1):
                insert_photo_row(
                    connection,
                    photo_id=item["id"],
                    case_id=case_id,
                    role=item["role"],
                    sequence=sequence,
                    original_name=item["original_name"],
                    stored_name=item["stored_name"],
                    stored_path=(new.relative_to(root) / item["stored_name"]).as_posix(),
                    sha256=item["sha256"],
                    size_bytes=item["size_bytes"],
                    width=item["width"],
                    height=item["height"],
                )
            connection.execute(
                "UPDATE cases SET photo_count=?,edit_revision=? WHERE id=?",
                (len(items), revision, case_id),
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK TO workspace_save")
            else:
                connection.execute("BEGIN IMMEDIATE")
            try:
                if journal:
                    recover_photo_edit(connection, journal, json.loads(journal.read_text("utf-8")))
            finally:
                connection.rollback()
            raise
    result = edit_detail(database, case_id, fallback_root)
    result["photo_backup"] = str(archive)
    try:
        if journal:
            journal.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        result["edit_warning"] = "已儲存；照片更正紀錄待下次啟動確認，請保留 case-edits 目錄"
    return result
