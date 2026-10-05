from __future__ import annotations

import os
import re
import sqlite3
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from ..config import BUILDINGS
from ..db import connect
from ..schemas import CaseCreate
from .errors import StorageError
from .naming import SCANNED_PHOTO_RE, role_from_filename, role_rank
from .photo_sync import (
    FolderIndex,
    list_images,
    read_image_info,
    refresh_case_from_folder,
    sync_case_photos,
)
from .records import insert_case_row, insert_photo_row

FLOOR_SUFFIX_RE = re.compile(r"^(?P<building>.+?)(?P<floor>B?\d+F|B\d+|RF)$", re.IGNORECASE)


def _split_building_details(remainder: str) -> tuple[str, list[str]]:
    """拆出棟別與 [樓層, 定址碼, 問題]；同時支援「二門診1F」連寫與舊的空白分隔。"""
    building = next(
        (
            value
            for value in sorted(BUILDINGS, key=len, reverse=True)
            if remainder.startswith(value)
        ),
        "",
    )
    if building:
        rest = remainder[len(building) :]
        if rest[:1].isspace():
            return building, rest.strip().split(maxsplit=2)
        first, *more = rest.split(maxsplit=2)
        return building, [first, *more] if first else []

    tokens = remainder.split(maxsplit=3)
    if len(tokens) == 4:
        return tokens[0], tokens[1:]
    if len(tokens) == 3:
        matched = FLOOR_SUFFIX_RE.match(tokens[0])
        if matched:
            return matched.group("building"), [matched.group("floor"), *tokens[1:]]
    return tokens[0] if tokens else "", []


def _case_from_folder(folder: Path) -> CaseCreate | None:
    folder_name = folder.name
    if re.match(r"^\d{4}-\d{2}-\d{2}_", folder_name):
        folder_name = folder_name.replace("_", " ")
    dated = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$", folder_name)
    try:
        if dated:
            work_date = date.fromisoformat(dated.group(1))
            remainder = dated.group(2)
        else:
            work_date = datetime.fromtimestamp(folder.stat().st_mtime).date()
            remainder = folder_name

        building, details = _split_building_details(remainder)
        if len(details) != 3:
            return None
        floor, address_code, issue_text = details
        issues = [item for item in issue_text.split("-") if item]
        if not issues:
            return None
        return CaseCreate(
            work_date=work_date,
            building=building,
            floor=floor,
            address_code=address_code,
            material=folder.parent.name,
            issues=issues,
        )
    except (OSError, ValueError):
        return None


def _fallback_case_from_folder(folder: Path) -> CaseCreate | None:
    try:
        return CaseCreate(
            work_date=datetime.fromtimestamp(folder.stat().st_mtime).date(),
            building="未辨識",
            floor="未辨識",
            address_code=folder.name[:60],
            material=folder.parent.name[:40] or "未辨識",
            issues=["未辨識"],
        )
    except (OSError, ValueError):
        return None


def _automatic_roles(count: int) -> list[str]:
    roles = ["中"] * count
    if count:
        roles[0] = "前"
    if count >= 2:
        roles[-1] = "後"
    if count >= 4:
        roles[-2] = "後"
    return roles


def _photos_from_folder(folder: Path) -> list[dict[str, object]]:
    entries = []
    for name, path in list_images(folder).items():
        info = read_image_info(path)
        if info is None:
            continue
        match = SCANNED_PHOTO_RE.fullmatch(name)
        sequence = int(match.group("sequence")) if match and match.group("sequence") else None
        entries.append((sequence, role_from_filename(name), name, info))
    # 有序號依序號；沒有序號則依 前、中、後、完成… 的角色順序，再依檔名
    entries.sort(
        key=lambda entry: (
            entry[0] if entry[0] is not None else 10**6,
            role_rank(entry[1]),
            entry[2].casefold(),
        )
    )
    defaults = _automatic_roles(len(entries))
    photos: list[dict[str, object]] = []
    for sequence, (_, role, name, info) in enumerate(entries, start=1):
        photos.append(
            {
                "sequence": sequence,
                "role": role or defaults[sequence - 1],
                "stored_name": name,
                "sha256": info.sha256,
                "size_bytes": info.size_bytes,
                "width": info.width,
                "height": info.height,
            }
        )
    return photos


def _relink_case(
    connection: sqlite3.Connection,
    case: sqlite3.Row,
    root: Path,
    folder: Path,
    photo_rows: list[sqlite3.Row],
) -> bool:
    """把案件重新指向新資料夾；資料庫唯一性衝突時回傳 False 並保持原狀。"""
    relative_folder = folder.relative_to(root).as_posix()
    connection.execute("SAVEPOINT relink_case")
    try:
        connection.execute(
            "UPDATE cases SET storage_root = ?, folder_path = ? WHERE id = ?",
            (str(root), relative_folder, case["id"]),
        )
        for photo in photo_rows:
            connection.execute(
                "UPDATE photos SET stored_path = ? WHERE case_id = ? AND stored_name = ?",
                (
                    (Path(relative_folder) / photo["stored_name"]).as_posix(),
                    case["id"],
                    photo["stored_name"],
                ),
            )
    except sqlite3.IntegrityError:
        connection.execute("ROLLBACK TO SAVEPOINT relink_case")
        connection.execute("RELEASE SAVEPOINT relink_case")
        return False
    connection.execute("RELEASE SAVEPOINT relink_case")
    return True


def rescan_case_locations(
    database_path: Path, scan_root: Path, *, prune: bool = True
) -> dict[str, int]:
    """Relink missing registered case folders found uniquely under the selected root.

    也會依檔案內容辨識被改名的案件資料夾與照片，並讓資料庫檔名、角色與實際圖檔一致。
    prune=False 時絕不刪除資料庫紀錄（自動掃描使用）；找不到資料夾或照片的紀錄原樣保留。
    """
    root = scan_root.resolve()
    if not root.is_dir():
        raise StorageError("掃描路徑不存在或不是資料夾")

    with connect(database_path) as connection:
        cases = connection.execute(
            "SELECT id, storage_root, folder_path FROM cases"
        ).fetchall()
        cases_to_relink = []
        unchanged = 0
        for case in cases:
            old_root = Path(case["storage_root"]).resolve()
            if old_root == root and (root / case["folder_path"]).is_dir():
                unchanged += 1
            else:
                cases_to_relink.append(case)

        wanted_names = {Path(case["folder_path"]).name.casefold() for case in cases_to_relink}
        matches: dict[str, list[Path]] = defaultdict(list)
        scanned_directories: list[Path] = []
        for current, directory_names, _ in os.walk(root, followlinks=False):
            directory_names[:] = [
                name for name in directory_names if not name.startswith(".")
            ]
            current_path = Path(current)
            if current_path != root:
                scanned_directories.append(current_path)
            if wanted_names:
                for name in directory_names:
                    if name.casefold() in wanted_names:
                        matches[name.casefold()].append(current_path / name)

        relinked = 0
        ambiguous = 0
        unresolved = 0
        removed = 0
        blocked_import_names: set[str] = set()
        occupied = {
            (Path(case["storage_root"]).resolve() / case["folder_path"]).resolve()
            for case in cases
            if (Path(case["storage_root"]).resolve() / case["folder_path"]).is_dir()
        }
        folder_index = FolderIndex(scanned_directories)
        for case in cases_to_relink:
            candidates = matches.get(Path(case["folder_path"]).name.casefold(), [])
            photo_rows = connection.execute(
                "SELECT stored_name, sha256, size_bytes FROM photos "
                "WHERE case_id = ? ORDER BY sequence",
                (case["id"],),
            ).fetchall()
            candidates = [
                candidate
                for candidate in candidates
                if all((candidate / photo["stored_name"]).is_file() for photo in photo_rows)
            ]
            if len(candidates) != 1:
                case_name = Path(case["folder_path"]).name.casefold()
                if len(candidates) > 1:
                    ambiguous += 1
                    blocked_import_names.add(case_name)
                else:
                    old_folder = Path(case["storage_root"]).resolve() / case["folder_path"]
                    if old_folder.is_dir():
                        unresolved += 1
                        blocked_import_names.add(case_name)
                    else:
                        # 原資料夾已不存在：依照片內容找出被改名／搬移的資料夾
                        content_matches = folder_index.find_matches(photo_rows, occupied)
                        if len(content_matches) == 1:
                            target = content_matches[0]
                            if _relink_case(connection, case, root, target, photo_rows):
                                occupied.add(target.resolve())
                                refresh_case_from_folder(
                                    connection, case["id"], target, root, _case_from_folder(target)
                                )
                                relinked += 1
                            else:
                                ambiguous += 1
                        elif len(content_matches) > 1:
                            ambiguous += 1
                        elif prune:
                            connection.execute("DELETE FROM cases WHERE id = ?", (case["id"],))
                            removed += 1
                continue

            if _relink_case(connection, case, root, candidates[0], photo_rows):
                occupied.add(candidates[0].resolve())
                relinked += 1
            else:
                ambiguous += 1

        photo_totals = {
            "photos_renamed": 0,
            "photos_added": 0,
            "photos_updated": 0,
            "photos_removed": 0,
        }
        for row in connection.execute("SELECT id, storage_root, folder_path FROM cases").fetchall():
            case_root = Path(row["storage_root"]).resolve()
            case_folder = (case_root / row["folder_path"]).resolve()
            inside_root = case_folder == root or root in case_folder.parents
            if not case_folder.is_dir() or not inside_root:
                continue
            for key, value in sync_case_photos(
                connection,
                case_id=row["id"],
                root=case_root,
                folder_path=row["folder_path"],
                prune=prune,
            ).items():
                photo_totals[key] += value

        registered_paths = {
            (Path(row["storage_root"]).resolve() / row["folder_path"]).resolve()
            for row in connection.execute("SELECT storage_root, folder_path FROM cases")
        }
        imported = 0
        skipped = 0
        for folder in scanned_directories:
            resolved_folder = folder.resolve()
            if (
                resolved_folder in registered_paths
                or folder.name.casefold() in blocked_import_names
            ):
                continue
            photos = _photos_from_folder(folder)
            if not photos:
                continue
            case = _case_from_folder(folder) or _fallback_case_from_folder(folder)
            if case is None:
                continue
            relative_folder = folder.relative_to(root).as_posix()
            case_id = str(uuid.uuid4())
            connection.execute("SAVEPOINT import_case")
            try:
                created_at = datetime.fromtimestamp(folder.stat().st_mtime, UTC).isoformat()
                insert_case_row(
                    connection,
                    case_id=case_id,
                    case=case,
                    storage_root=str(root),
                    folder_path=relative_folder,
                    photo_count=len(photos),
                    created_at=created_at,
                )
                for photo in photos:
                    stored_name = str(photo["stored_name"])
                    insert_photo_row(
                        connection,
                        photo_id=str(uuid.uuid4()),
                        case_id=case_id,
                        role=str(photo["role"]),
                        sequence=int(photo["sequence"]),
                        original_name=stored_name,
                        stored_name=stored_name,
                        stored_path=(Path(relative_folder) / stored_name).as_posix(),
                        sha256=str(photo["sha256"]),
                        size_bytes=int(photo["size_bytes"]),
                        width=int(photo["width"]),
                        height=int(photo["height"]),
                    )
                connection.execute("RELEASE SAVEPOINT import_case")
                registered_paths.add(resolved_folder)
                imported += 1
            except (OSError, sqlite3.IntegrityError):
                connection.execute("ROLLBACK TO SAVEPOINT import_case")
                connection.execute("RELEASE SAVEPOINT import_case")
                skipped += 1
        connection.commit()

    return {
        "registered": len(cases),
        "unchanged": unchanged,
        "relinked": relinked,
        "imported": imported,
        "removed": removed,
        "unresolved": unresolved,
        "ambiguous": ambiguous,
        "skipped": skipped,
        **photo_totals,
    }
