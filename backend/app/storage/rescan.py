from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..config import ALLOWED_IMAGE_FORMATS, BUILDINGS, PHOTO_ROLES
from ..db import connect
from ..schemas import CaseCreate
from .errors import StorageError
from .records import insert_case_row, insert_photo_row

SCANNED_PHOTO_RE = re.compile(
    rf"^(?P<sequence>\d+)_"
    rf"(?P<role>{'|'.join(re.escape(role) for role in PHOTO_ROLES)})"
    r"(?:-\d+)?\.(?:jpe?g|png|webp)$",
    re.IGNORECASE,
)


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
        roles[-1] = "完成"
    if count >= 4:
        roles[-2] = "後"
    return roles


def _photos_from_folder(folder: Path) -> list[dict[str, object]]:
    photos: list[dict[str, object]] = []
    try:
        files = sorted(folder.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return []
    for path in files:
        match = SCANNED_PHOTO_RE.fullmatch(path.name)
        if (
            path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}
            or not path.is_file()
        ):
            continue
        try:
            with path.open("rb") as photo_file:
                digest = hashlib.file_digest(photo_file, "sha256").hexdigest()
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
            if image_format not in ALLOWED_IMAGE_FORMATS or width < 1 or height < 1:
                continue
            photos.append(
                {
                    "sequence": int(match.group("sequence")) if match else len(photos) + 1,
                    "role": match.group("role") if match else "",
                    "stored_name": path.name,
                    "sha256": digest,
                    "size_bytes": path.stat().st_size,
                    "width": width,
                    "height": height,
                }
            )
        except (OSError, UnidentifiedImageError):
            continue
    photos.sort(
        key=lambda photo: (int(photo["sequence"]), str(photo["stored_name"]).casefold())
    )
    defaults = _automatic_roles(len(photos))
    for sequence, photo in enumerate(photos, start=1):
        photo["sequence"] = sequence
        if not photo["role"]:
            photo["role"] = defaults[sequence - 1]
    return photos


def rescan_case_locations(
    database_path: Path, scan_root: Path, *, prune: bool = True
) -> dict[str, int]:
    """Relink missing registered case folders found uniquely under the selected root.

    prune=False 時絕不刪除資料庫紀錄（自動掃描使用）；找不到資料夾的案件原樣保留。
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
        for case in cases_to_relink:
            candidates = matches.get(Path(case["folder_path"]).name.casefold(), [])
            photo_rows = connection.execute(
                "SELECT stored_name FROM photos WHERE case_id = ? ORDER BY sequence",
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
                    elif prune:
                        connection.execute("DELETE FROM cases WHERE id = ?", (case["id"],))
                        removed += 1
                continue

            relative_folder = candidates[0].relative_to(root).as_posix()
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
                relinked += 1
            except sqlite3.IntegrityError:
                ambiguous += 1

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
    }
