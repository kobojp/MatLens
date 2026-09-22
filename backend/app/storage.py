from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from .config import ALLOWED_IMAGE_FORMATS, BUILDINGS, MAX_PHOTO_BYTES, PHOTO_ROLES
from .db import connect
from .schemas import CaseCreate

INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class StorageError(Exception):
    pass


class DuplicatePhotoError(StorageError):
    def __init__(self, duplicates: list[dict[str, str]]) -> None:
        super().__init__("發現重複照片")
        self.duplicates = duplicates


def sanitize_component(value: str, fallback: str = "未填", max_length: int = 80) -> str:
    value = INVALID_WINDOWS_CHARS.sub("-", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    if value.upper().split(".")[0] in WINDOWS_RESERVED_NAMES:
        value = f"_{value}"
    return value[:max_length].rstrip(" .") or fallback


def validate_directory_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or len(name) > 80
        or INVALID_WINDOWS_CHARS.search(name)
        or name.endswith((" ", "."))
        or name.upper().split(".")[0] in WINDOWS_RESERVED_NAMES
    ):
        raise StorageError(f"目錄名稱不安全：{value}")
    return name


def _direct_child(root: Path, name: str) -> Path:
    root = root.resolve()
    candidate = (root / validate_directory_name(name)).resolve()
    if root not in candidate.parents:
        raise StorageError("目錄必須位於照片儲存目錄內")
    return candidate


def validate_month_directory_name(value: str) -> str:
    name = validate_directory_name(value)
    if not re.fullmatch(r"(?:0?[1-9]|1[0-2])月", name):
        raise StorageError("月份目錄名稱必須是 1月 到 12月")
    return name


def _visible_directories(root: Path) -> list[Path]:
    root = root.resolve()
    directories: list[Path] = []
    try:
        entries = root.iterdir()
        for entry in entries:
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            resolved = entry.resolve()
            if root in resolved.parents:
                directories.append(entry)
    except OSError as error:
        raise StorageError("無法掃描照片儲存目錄") from error
    return sorted(directories, key=lambda path: path.name.casefold())


def scan_storage_tree(photo_root: Path, target_month: str) -> dict[str, object]:
    root = photo_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    month_paths = [
        month
        for month in _visible_directories(root)
        if re.fullmatch(r"(?:0?[1-9]|1[0-2])月", month.name)
    ]
    month_paths.sort(key=lambda path: int(path.name.removesuffix("月")))
    months = [
        {
            "name": month.name,
            "subfolders": [folder.name for folder in _visible_directories(month)],
        }
        for month in month_paths
    ]
    return {
        "root": str(root),
        "target_month": target_month,
        "month_exists": any(month["name"] == target_month for month in months),
        "months": months,
    }


def create_storage_folders(
    photo_root: Path, month: str, subfolders: list[str]
) -> dict[str, object]:
    root = photo_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    month_path = _direct_child(root, validate_month_directory_name(month))
    names = [validate_directory_name(name) for name in subfolders]
    try:
        month_path.mkdir(exist_ok=True)
        if not month_path.is_dir():
            raise StorageError(f"{month} 不是資料夾")
        for name in names:
            subfolder = _direct_child(month_path, name)
            subfolder.mkdir(exist_ok=True)
            if not subfolder.is_dir():
                raise StorageError(f"{name} 不是資料夾")
    except OSError as error:
        raise StorageError("無法建立月份或子目錄") from error
    return {
        "root": str(root),
        "month": {
            "name": month_path.name,
            "subfolders": [folder.name for folder in _visible_directories(month_path)],
        },
    }


def resolve_storage_destination(photo_root: Path, month: str, subfolder: str) -> Path:
    root = photo_root.resolve()
    month_path = _direct_child(root, validate_month_directory_name(month))
    destination = _direct_child(month_path, subfolder)
    if not month_path.is_dir() or not destination.is_dir():
        raise StorageError("選擇的月份或子目錄不存在，請重新掃描或先建立")
    return destination


def scan_directory_subfolders(scan_path: Path) -> dict[str, object]:
    """掃描指定路徑的第一層可見子目錄，不需月份結構。"""
    target = scan_path.resolve()
    if not target.is_dir():
        raise StorageError("指定路徑不存在或不是資料夾")
    subfolders = [folder.name for folder in _visible_directories(target)]
    return {
        "root": str(target),
        "subfolders": subfolders,
    }


def resolve_free_destination(scan_root: Path, subfolder: str) -> Path:
    """驗證並回傳自由路徑模式下的目的地資料夾。"""
    root = scan_root.resolve()
    if not root.is_dir():
        raise StorageError("掃描根目錄不存在")
    destination = _direct_child(root, subfolder)
    if not destination.is_dir():
        raise StorageError("選擇的子目錄不存在，請重新掃描")
    return destination


def completeness(roles: list[str]) -> dict[str, object]:
    missing = [role for role in ["前", "中"] if role not in roles]
    if not ({"後", "完成"} & set(roles)):
        missing.append("後／完成")
    return {"is_complete": not missing, "missing_roles": missing}


def _case_folder_name(case: CaseCreate, *, include_date: bool = True) -> str:
    issue_text = "-".join(case.issues)
    parts = [
        sanitize_component(case.building),
        sanitize_component(case.floor),
        sanitize_component(case.address_code),
        sanitize_component(issue_text),
    ]
    if include_date:
        parts = [case.work_date.isoformat()] + parts
    return " ".join(parts)


def _available_case_path(
    photo_root: Path,
    destination: Path,
    case: CaseCreate,
    database_path: Path,
    *,
    include_date: bool = True,
) -> Path:
    name = _case_folder_name(case, include_date=include_date)
    candidate = destination / name
    suffix = 2
    with connect(database_path) as connection:
        existing_paths = {
            row["folder_path"]
            for row in connection.execute("SELECT folder_path FROM cases").fetchall()
    }
    while candidate.exists() or candidate.relative_to(photo_root).as_posix() in existing_paths:
        candidate = destination / f"{name}-{suffix:02d}"
        suffix += 1
    return candidate


def _stored_names(roles: list[str], extensions: list[str]) -> list[str]:
    totals = Counter(roles)
    seen: defaultdict[str, int] = defaultdict(int)
    names: list[str] = []
    for index, (role, extension) in enumerate(zip(roles, extensions, strict=True), start=1):
        seen[role] += 1
        role_name = role
        if totals[role] > 1:
            role_name = f"{role}-{seen[role]:02d}"
        names.append(f"{index:02d}_{sanitize_component(role_name)}{extension.lower()}")
    return names


async def _save_upload(upload: UploadFile, target: Path) -> tuple[str, int, int, int, str]:
    digest = hashlib.sha256()
    total = 0
    with target.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_PHOTO_BYTES:
                raise StorageError(f"{upload.filename or '照片'} 超過 25 MB")
            digest.update(chunk)
            output.write(chunk)

    try:
        with Image.open(target) as image:
            image.verify()
        with Image.open(target) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
    except (UnidentifiedImageError, OSError) as error:
        raise StorageError(f"{upload.filename or '檔案'} 不是可讀取的圖片") from error

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise StorageError(f"不支援 {image_format or '未知'} 圖片格式")
    if width < 1 or height < 1:
        raise StorageError("圖片尺寸無效")

    extension = ".jpg" if image_format == "JPEG" else f".{image_format.lower()}"
    return digest.hexdigest(), total, width, height, extension


async def create_case(
    *,
    database_path: Path,
    photo_root: Path,
    case: CaseCreate,
    uploads: list[UploadFile],
    roles: list[str],
    storage_month: str,
    storage_subfolder: str,
    free_mode: bool = False,
    include_date: bool = True,
) -> dict[str, object]:
    if not uploads:
        raise StorageError("至少需要一張照片")
    if len(uploads) != len(roles):
        raise StorageError("照片與分類數量不一致")
    if len(uploads) > 30:
        raise StorageError("單一案件最多 30 張照片")
    unknown_roles = sorted(set(roles) - set(PHOTO_ROLES))
    if unknown_roles:
        raise StorageError(f"未知照片分類：{', '.join(unknown_roles)}")

    photo_root.mkdir(parents=True, exist_ok=True)
    if free_mode:
        destination = resolve_free_destination(photo_root, storage_subfolder)
    else:
        destination = resolve_storage_destination(
            photo_root, storage_month, storage_subfolder
        )
    staging_root = photo_root / ".staging"
    staging_root.mkdir(exist_ok=True)
    staging_dir = staging_root / str(uuid.uuid4())
    staging_dir.mkdir()
    staged: list[dict[str, object]] = []

    try:
        for index, upload in enumerate(uploads, start=1):
            temporary_path = staging_dir / f"upload-{index:02d}.bin"
            sha256, size, width, height, extension = await _save_upload(
                upload, temporary_path
            )
            staged.append(
                {
                    "temporary_path": temporary_path,
                    "original_name": upload.filename or f"photo-{index}",
                    "sha256": sha256,
                    "size_bytes": size,
                    "width": width,
                    "height": height,
                    "extension": extension,
                }
            )

        hashes = [str(item["sha256"]) for item in staged]
        if len(hashes) != len(set(hashes)):
            raise DuplicatePhotoError(
                [{"original_name": "本次選取中有相同照片", "case_id": ""}]
            )

        placeholders = ",".join("?" for _ in hashes)
        duplicates: list[dict[str, str]] = []
        with connect(database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT photos.sha256, photos.original_name, photos.case_id,
                       cases.building, cases.floor, cases.address_code
                FROM photos
                JOIN cases ON cases.id = photos.case_id
                WHERE photos.sha256 IN ({placeholders})
                """,
                hashes,
            ).fetchall()
            duplicates = [
                {
                    "original_name": row["original_name"],
                    "case_id": row["case_id"],
                    "case_label": (
                        f"{row['building']} {row['floor']} {row['address_code']}"
                    ),
                }
                for row in rows
            ]
        if duplicates:
            raise DuplicatePhotoError(duplicates)

        extensions = [str(item["extension"]) for item in staged]
        stored_names = _stored_names(roles, extensions)
        for item, stored_name in zip(staged, stored_names, strict=True):
            temporary_path = Path(str(item["temporary_path"]))
            temporary_path.rename(staging_dir / stored_name)
            item["stored_name"] = stored_name

        final_dir = _available_case_path(
            photo_root, destination, case, database_path, include_date=include_date
        )
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_dir, final_dir)

        case_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()
        relative_folder = final_dir.relative_to(photo_root).as_posix()
        try:
            with connect(database_path) as connection:
                connection.execute("BEGIN")
                connection.execute(
                    """
                    INSERT INTO cases (
                        id, work_date, building, floor, address_code, material,
                        issues_json, location, notes, storage_root, folder_path,
                        photo_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        case.work_date.isoformat(),
                        case.building,
                        case.floor,
                        case.address_code,
                        case.material,
                        json.dumps(case.issues, ensure_ascii=False),
                        case.location,
                        case.notes,
                        str(photo_root.resolve()),
                        relative_folder,
                        len(staged),
                        created_at,
                    ),
                )
                for sequence, (item, role) in enumerate(
                    zip(staged, roles, strict=True), start=1
                ):
                    photo_id = str(uuid.uuid4())
                    stored_name = str(item["stored_name"])
                    stored_path = (Path(relative_folder) / stored_name).as_posix()
                    connection.execute(
                        """
                        INSERT INTO photos (
                            id, case_id, role, sequence, original_name, stored_name,
                            stored_path, sha256, size_bytes, width, height
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            photo_id,
                            case_id,
                            role,
                            sequence,
                            str(item["original_name"]),
                            stored_name,
                            stored_path,
                            str(item["sha256"]),
                            int(item["size_bytes"]),
                            int(item["width"]),
                            int(item["height"]),
                        ),
                    )
                connection.commit()
        except Exception:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise

        return get_case(database_path, case_id)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _case_row_to_dict(row: object, roles: list[str] | None = None) -> dict[str, object]:
    data = dict(row)  # type: ignore[arg-type]
    data["issues"] = json.loads(data.pop("issues_json"))
    if roles is not None:
        data.update(completeness(roles))
    return data


def get_case(database_path: Path, case_id: str) -> dict[str, object]:
    with connect(database_path) as connection:
        case_row = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if case_row is None:
            raise KeyError(case_id)
        photo_rows = connection.execute(
            "SELECT * FROM photos WHERE case_id = ? ORDER BY sequence", (case_id,)
        ).fetchall()

    result = _case_row_to_dict(case_row, [row["role"] for row in photo_rows])
    result["photos"] = [
        {
            **dict(row),
            "content_url": f"/api/photos/{row['id']}/content",
        }
        for row in photo_rows
    ]
    return result


def list_cases(
    database_path: Path,
    *,
    query: str = "",
    building: str = "",
    material: str = "",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, object]], int]:
    clauses: list[str] = []
    parameters: list[object] = []
    if query:
        wildcard = f"%{query}%"
        clauses.append(
            "(building LIKE ? OR floor LIKE ? OR address_code LIKE ? "
            "OR material LIKE ? OR issues_json LIKE ? OR location LIKE ? OR notes LIKE ?)"
        )
        parameters.extend([wildcard] * 7)
    if building:
        clauses.append("building = ?")
        parameters.append(building)
    if material:
        clauses.append("material = ?")
        parameters.append(material)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(database_path) as connection:
        total = int(
            connection.execute(
                f"SELECT COUNT(*) FROM cases {where}", parameters
            ).fetchone()[0]
        )
        rows = connection.execute(
            f"SELECT * FROM cases {where} "
            "ORDER BY work_date DESC, created_at DESC LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
        results: list[dict[str, object]] = []
        for row in rows:
            role_rows = connection.execute(
                "SELECT role FROM photos WHERE case_id = ? ORDER BY sequence", (row["id"],)
            ).fetchall()
            results.append(_case_row_to_dict(row, [role["role"] for role in role_rows]))
    return results, total


SCANNED_PHOTO_RE = re.compile(
    rf"^(?P<sequence>\d+)_"
    rf"(?P<role>{'|'.join(re.escape(role) for role in PHOTO_ROLES)})"
    r"(?:-\d+)?\.(?:jpe?g|png|webp)$",
    re.IGNORECASE,
)


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

        building = next(
            (
                value
                for value in sorted(BUILDINGS, key=len, reverse=True)
                if remainder == value or remainder.startswith(f"{value} ")
            ),
            "",
        )
        if building:
            details = remainder[len(building) :].strip().split(maxsplit=2)
        else:
            first, *details = remainder.split(maxsplit=1)
            building = first
            details = details[0].split(maxsplit=2) if details else []
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


def rescan_case_locations(database_path: Path, scan_root: Path) -> dict[str, int]:
    """Relink missing registered case folders found uniquely under the selected root."""
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
                    else:
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
                connection.execute(
                    """
                    INSERT INTO cases (
                        id, work_date, building, floor, address_code, material,
                        issues_json, location, notes, storage_root, folder_path,
                        photo_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        case.work_date.isoformat(),
                        case.building,
                        case.floor,
                        case.address_code,
                        case.material,
                        json.dumps(case.issues, ensure_ascii=False),
                        str(root),
                        relative_folder,
                        len(photos),
                        created_at,
                    ),
                )
                for photo in photos:
                    stored_name = str(photo["stored_name"])
                    connection.execute(
                        """
                        INSERT INTO photos (
                            id, case_id, role, sequence, original_name, stored_name,
                            stored_path, sha256, size_bytes, width, height
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            case_id,
                            photo["role"],
                            photo["sequence"],
                            stored_name,
                            stored_name,
                            (Path(relative_folder) / stored_name).as_posix(),
                            photo["sha256"],
                            photo["size_bytes"],
                            photo["width"],
                            photo["height"],
                        ),
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
