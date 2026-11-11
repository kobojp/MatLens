"""Update one existing case; never upload, recompress or overwrite its photos."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from ..db import connect
from ..schemas import CaseEdit
from .cases import _case_folder_name, get_case
from .errors import StorageError


class EditConflict(StorageError):
    pass


def _checked_folder(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not root.is_absolute() or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise StorageError("案件路徑不在原儲存目錄內")
    folder = root / relative
    if root.resolve() not in folder.resolve().parents:
        raise StorageError("案件路徑不在原儲存目錄內")
    for part in [root, *[p for p in folder.parents if root in p.parents], folder]:
        if part.is_symlink() or part.is_junction():
            raise StorageError("案件路徑包含連結或重新導向，不能編輯")
    if must_exist and not folder.is_dir():
        raise EditConflict("案件資料夾已不存在，請重新掃描及載入")
    return folder


def _files(folder: Path) -> list:
    result = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise StorageError("案件內含連結，不能更名")
        if path.is_file():
            stat = path.stat()
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            result.append(
                [path.relative_to(folder).as_posix(), stat.st_size, stat.st_mtime_ns, digest]
            )
    return result


def _snapshot(connection, case_id: str, fallback_root: Path) -> tuple:
    row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if row is None:
        raise KeyError(case_id)
    case = dict(row)
    root = Path(case["storage_root"] or fallback_root)
    folder = _checked_folder(root, case["folder_path"])
    photos = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM photos WHERE case_id=? ORDER BY sequence", (case_id,)
        )
    ]
    for photo in photos:
        if (
            Path(photo["stored_name"]).name != photo["stored_name"]
            or not (folder / photo["stored_name"]).is_file()
        ):
            raise EditConflict("照片紀錄與磁碟不一致，請先掃描並重新載入案件")
    files = _files(folder)
    token = hashlib.sha256(json.dumps([case, photos, files], sort_keys=True).encode()).hexdigest()
    return case, root, folder, token


def _naming(case: dict, folder: Path) -> dict:
    if case["naming_json"]:
        return json.loads(case["naming_json"])
    return {
        "include_date": bool(re.match(r"^\d{4}-\d{2}-\d{2}[ _]", folder.name)),
        "include_material": f"{case['address_code']} {case['material']} " in folder.name,
        "separator": "-" if "火警-" in folder.name else " ",
    }


def edit_detail(database: Path, case_id: str, fallback_root: Path) -> dict:
    with closing(connect(database)) as connection:
        case, root, folder, token = _snapshot(connection, case_id, fallback_root)
    details = get_case(database, case_id)
    return {
        **details,
        "storage_root": str(root),
        "name_with_sequence": bool(details["photos"]) and all(
            re.match(r"^\d+_", photo["stored_name"]) for photo in details["photos"]
        ),
        "edit_token": token,
        "original_path": str(folder),
        "naming": _naming(case, folder),
        "requires_managed_confirmation": not bool(case["app_managed"]),
    }


def _plan(connection, case_id: str, change: CaseEdit, fallback_root: Path) -> tuple:
    case, root, old, token = _snapshot(connection, case_id, fallback_root)
    if token != change.token:
        raise EditConflict("案件或磁碟內容已變更，請重新載入後再編輯")
    naming = _naming(case, old)
    keys = ["work_date", "building", "floor", "address_code", "material", "issues"]
    previous = {**case, "issues": json.loads(case["issues_json"])}
    values = change.model_dump(mode="json")
    changed = any(previous[key] != values[key] for key in keys)
    if change.apply_naming:
        naming = {
            "include_date": change.include_date,
            "include_material": change.include_material,
            "separator": " ",
        }
    name = _case_folder_name(
        change,
        include_date=naming["include_date"],
        include_material=naming["include_material"],
        issue_separator=naming["separator"],
    )
    new = old.with_name(name) if changed or change.apply_naming else old
    _checked_folder(root, new.relative_to(root).as_posix(), must_exist=False)
    if new != old:
        occupied = connection.execute(
            "SELECT id FROM cases WHERE folder_path=? AND id!=?",
            (new.relative_to(root).as_posix(), case_id),
        ).fetchone()
        if new.exists() or occupied:
            raise EditConflict("新資料夾名稱已存在，請修改名稱；不會覆蓋其他案件")
    return case, root, old, new, naming


def preview_edit(database: Path, case_id: str, change: CaseEdit, fallback_root: Path) -> dict:
    with closing(connect(database)) as connection:
        case, root, old, new, naming = _plan(connection, case_id, change, fallback_root)
    from .workspace_edit import photo_change_plan
    with closing(connect(database)) as connection:
        photo_changes = photo_change_plan(connection, case_id, change)
    return {
        **photo_changes,
        "old_path": str(old),
        "new_path": str(new),
        "rename": old != new,
        "requires_managed_confirmation": not bool(case["app_managed"]),
    }


def _journal(database: Path, case_id: str, old: Path, new: Path, root: Path | None = None) -> Path:
    directory = database.parent / "case-edits"
    directory.mkdir(exist_ok=True)
    path = directory / (uuid.uuid4().hex + ".json")
    with closing(connect(database)) as connection:
        row = connection.execute(
            "SELECT storage_root, folder_path FROM cases WHERE id=?", (case_id,)
        ).fetchone()
    payload = {
        "case_id": case_id,
        "root": str(root or Path(row["storage_root"])),
        "old": str(old),
        "new": str(new),
        "files": _files(old),
    }
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    return path


def recover_edits(database: Path) -> None:
    """A SQLite write lock excludes live edits; DB commit decides rename recovery."""
    for path in (database.parent / "case-edits").glob("*.json"):
        with closing(connect(database)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not path.exists():
                    connection.rollback()
                    continue
                job = json.loads(path.read_text("utf-8"))
                if job.get("kind") == "photos":
                    from .workspace_edit import recover_photo_edit
                    recover_photo_edit(connection, path, job)
                    connection.commit()
                    continue
                root = Path(job["root"])
                old = _checked_folder(
                    root, Path(job["old"]).relative_to(root).as_posix(), must_exist=False
                )
                new = _checked_folder(
                    root, Path(job["new"]).relative_to(root).as_posix(), must_exist=False
                )
                row = connection.execute(
                    "SELECT folder_path, storage_root FROM cases WHERE id=?", (job["case_id"],)
                ).fetchone()
                if row is None or Path(row["storage_root"] or job["root"]) != root:
                    raise StorageError("案件更名恢復資訊不一致，請保留 case-edits 紀錄")
                if old != new and old.exists() and new.exists():
                    raise StorageError("更名恢復出現兩個資料夾，請保留紀錄並確認精確目標")
                current = root / row["folder_path"]
                if current == old and not old.exists() and new.is_dir():
                    if _files(new) != job["files"]:
                        raise StorageError("中斷更名的資料夾內容已變更，停止自動恢復")
                    new.rename(old)
                elif current not in (old, new) or not current.is_dir():
                    raise StorageError("案件更名恢復路徑不確定，請保留 case-edits 紀錄")
                path.unlink()
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def _write_case(connection, case_id: str, change: CaseEdit, relative: str, naming: dict) -> None:
    connection.execute(
        """UPDATE cases SET work_date=?, building=?, floor=?, address_code=?,
        material=?, issues_json=?, location=?, notes=?, folder_path=?, naming_json=?,
        metadata_authoritative=1 WHERE id=?""",
        (
            change.work_date.isoformat(),
            change.building,
            change.floor,
            change.address_code,
            change.material,
            json.dumps(change.issues, ensure_ascii=False),
            change.location,
            change.notes,
            relative,
            json.dumps(naming),
            case_id,
        ),
    )
    for row in connection.execute("SELECT id, stored_name FROM photos WHERE case_id=?", (case_id,)):
        connection.execute(
            "UPDATE photos SET stored_path=? WHERE id=?",
            ((Path(relative) / row["stored_name"]).as_posix(), row["id"]),
        )


def update_case(database: Path, case_id: str, change: CaseEdit, fallback_root: Path) -> dict:
    journal = None
    moved = False
    with closing(connect(database)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            case, root, old, new, naming = _plan(connection, case_id, change, fallback_root)
            if new != old and not case["app_managed"] and not change.confirm_managed:
                raise EditConflict("請確認這是整理後的案件資料夾，非原始來源照片目錄")
            backups = database.parent / "backups"
            backups.mkdir(exist_ok=True)
            with (
                closing(connect(database)) as source,
                closing(
                    sqlite3.connect(backups / ("before-case-edit-" + uuid.uuid4().hex + ".db"))
                ) as backup,
            ):
                source.backup(backup)
            if _snapshot(connection, case_id, fallback_root)[3] != change.token:
                raise EditConflict("備份期間案件內容已變更，請重新載入")
            if new != old:
                journal = _journal(database, case_id, old, new, root)
                if new.exists():
                    raise EditConflict("目標已存在，請重新載入")
                old.rename(new)
                moved = True
            _write_case(connection, case_id, change, new.relative_to(root).as_posix(), naming)
            connection.commit()
        except Exception:
            connection.rollback()
            if moved:
                if old.exists() or not new.is_dir():
                    raise StorageError("更名回復受阻，請保留 case-edits 紀錄並重新啟動") from None
                new.rename(old)
            if journal:
                journal.unlink()
            raise
    result = get_case(database, case_id)
    if journal:
        try:
            journal.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            result["edit_warning"] = "案件已更新；更名紀錄待下次啟動確認，請保留 case-edits 目錄"
    return result
