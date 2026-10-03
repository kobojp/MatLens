from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from ..config import ALLOWED_IMAGE_FORMATS, MAX_PHOTO_BYTES, PHOTO_ROLES
from ..db import connect
from ..schemas import CaseCreate
from .errors import DuplicatePhotoError, StorageError
from .paths import resolve_free_destination, resolve_storage_destination, sanitize_component
from .records import insert_case_row, insert_photo_row


def completeness(roles: list[str]) -> dict[str, object]:
    missing = [role for role in ["前", "中"] if role not in roles]
    if not ({"後", "完成"} & set(roles)):
        missing.append("後／完成")
    return {"is_complete": not missing, "missing_roles": missing}


def _case_folder_name(case: CaseCreate, *, include_date: bool = True) -> str:
    issue_text = "-".join(case.issues)
    parts = [
        sanitize_component(case.building) + sanitize_component(case.floor),
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
                insert_case_row(
                    connection,
                    case_id=case_id,
                    case=case,
                    storage_root=str(photo_root.resolve()),
                    folder_path=relative_folder,
                    photo_count=len(staged),
                    created_at=created_at,
                )
                for sequence, (item, role) in enumerate(
                    zip(staged, roles, strict=True), start=1
                ):
                    stored_name = str(item["stored_name"])
                    insert_photo_row(
                        connection,
                        photo_id=str(uuid.uuid4()),
                        case_id=case_id,
                        role=role,
                        sequence=sequence,
                        original_name=str(item["original_name"]),
                        stored_name=stored_name,
                        stored_path=(Path(relative_folder) / stored_name).as_posix(),
                        sha256=str(item["sha256"]),
                        size_bytes=int(item["size_bytes"]),
                        width=int(item["width"]),
                        height=int(item["height"]),
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
