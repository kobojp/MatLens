"""掃描時讓資料庫與磁碟上的案件資料夾保持一致。

以檔案內容（SHA-256）辨識被使用者改名的照片與被改名的案件資料夾，
所以不依賴檔名。只讀取照片，從不修改、搬移或刪除任何檔案。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..config import ALLOWED_IMAGE_FORMATS
from ..schemas import CaseCreate
from .naming import role_from_filename
from .records import insert_photo_row

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class ImageInfo:
    sha256: str
    size_bytes: int
    width: int
    height: int


def list_images(folder: Path) -> dict[str, Path]:
    """資料夾第一層的圖檔，檔名 -> 路徑。"""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return {}
    return {
        path.name: path
        for path in entries
        if path.suffix.casefold() in IMAGE_SUFFIXES and path.is_file()
    }


def file_sha256(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError:
        return None


def read_image_info(path: Path) -> ImageInfo | None:
    """驗證圖檔並回傳雜湊與尺寸；不是可讀取的支援圖片時回傳 None。"""
    digest = file_sha256(path)
    if digest is None:
        return None
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
        size = path.stat().st_size
    except (OSError, UnidentifiedImageError):
        return None
    if image_format not in ALLOWED_IMAGE_FORMATS or width < 1 or height < 1:
        return None
    return ImageInfo(digest, size, width, height)


class FolderIndex:
    """替「依內容尋找被改名的案件資料夾」快取圖檔清單與雜湊。"""

    def __init__(self, directories: list[Path]) -> None:
        self._directories = directories
        self._images: dict[Path, dict[str, Path]] = {}
        self._hashes: dict[Path, str | None] = {}

    def _listing(self, folder: Path) -> dict[str, Path]:
        if folder not in self._images:
            self._images[folder] = list_images(folder)
        return self._images[folder]

    def _hash(self, path: Path) -> str | None:
        if path not in self._hashes:
            self._hashes[path] = file_sha256(path)
        return self._hashes[path]

    def find_matches(
        self, rows: list[sqlite3.Row], excluded: set[Path]
    ) -> list[Path]:
        """回傳與案件照片共享至少一張相同內容的資料夾。"""
        wanted_hashes = {row["sha256"] for row in rows}
        wanted_sizes = {int(row["size_bytes"]) for row in rows}
        found: list[Path] = []
        for folder in self._directories:
            if folder.resolve() in excluded:
                continue
            for path in self._listing(folder).values():
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size in wanted_sizes and self._hash(path) in wanted_hashes:
                    found.append(folder)
                    break
        return found


_DATED_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ _]")


def refresh_case_from_folder(
    connection: sqlite3.Connection, case_id: str, folder: Path, root: Path, parsed: object
) -> None:
    """資料夾被改名／搬移後，依新資料夾名稱更新棟別、樓層、定址碼、問題等欄位。

    只在能解析出完整案件資訊時更新；備註與補充位置不變。
    """
    if not isinstance(parsed, CaseCreate):
        return
    work_date = parsed.work_date.isoformat() if _DATED_NAME_RE.match(folder.name) else None
    material = folder.parent.name if folder.parent != root and folder.parent.name else None
    connection.execute(
        """
        UPDATE cases SET building = ?, floor = ?, address_code = ?, issues_json = ?,
            work_date = COALESCE(?, work_date), material = COALESCE(?, material)
        WHERE id = ?
        """,
        (
            parsed.building,
            parsed.floor,
            parsed.address_code,
            json.dumps(parsed.issues, ensure_ascii=False),
            work_date,
            material,
            case_id,
        ),
    )


def sync_case_photos(
    connection: sqlite3.Connection,
    *,
    case_id: str,
    root: Path,
    folder_path: str,
    prune: bool,
) -> dict[str, int]:
    """讓單一案件的照片紀錄與資料夾內實際圖檔一致。

    - 檔名相同、大小相同：視為未變更（不重新計算雜湊）。
    - 檔名相同、大小不同：視為內容被編修，更新雜湊與尺寸。
    - 檔名消失但內容雜湊出現在別的檔名：視為改名，更新檔名、路徑，並依新檔名更新角色。
    - 新圖檔：加入案件（內容與其他照片重複者略過）。
    - 找不到對應檔案的紀錄：prune=True 才刪除，否則保留。
    """
    counts = {"photos_renamed": 0, "photos_added": 0, "photos_updated": 0, "photos_removed": 0}
    folder = (root / folder_path).resolve()
    rows = connection.execute(
        "SELECT id, role, sequence, stored_name, sha256, size_bytes "
        "FROM photos WHERE case_id = ? ORDER BY sequence",
        (case_id,),
    ).fetchall()
    on_disk = list_images(folder)

    unmatched_rows = []
    for row in rows:
        path = on_disk.pop(row["stored_name"], None)
        if path is None:
            unmatched_rows.append(row)
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size != row["size_bytes"]:
            info = read_image_info(path)
            if info is not None:
                connection.execute(
                    "UPDATE photos SET sha256 = ?, size_bytes = ?, width = ?, height = ? "
                    "WHERE id = ?",
                    (info.sha256, info.size_bytes, info.width, info.height, row["id"]),
                )
                counts["photos_updated"] += 1

    # 用內容雜湊辨識改名
    remaining_by_hash: dict[str, list[Path]] = {}
    for path in on_disk.values():
        digest = file_sha256(path)
        if digest is not None:
            remaining_by_hash.setdefault(digest, []).append(path)
    renames: list[tuple[sqlite3.Row, Path]] = []
    missing_rows = []
    for row in unmatched_rows:
        candidates = remaining_by_hash.get(row["sha256"], [])
        if candidates:
            renames.append((row, candidates.pop(0)))
        else:
            missing_rows.append(row)

    if renames:
        # stored_path 有 UNIQUE：兩階段更新，避免互換檔名時暫時衝突
        for row, _ in renames:
            connection.execute(
                "UPDATE photos SET stored_path = ? WHERE id = ?",
                (f"\x00rename/{row['id']}", row["id"]),
            )
        for row, path in renames:
            new_role = role_from_filename(path.name) or row["role"]
            connection.execute(
                "UPDATE photos SET stored_name = ?, stored_path = ?, role = ? WHERE id = ?",
                (path.name, (Path(folder_path) / path.name).as_posix(), new_role, row["id"]),
            )
            counts["photos_renamed"] += 1

    # 新增的圖檔
    max_sequence = max((int(row["sequence"]) for row in rows), default=0)
    known_hashes = {
        found["sha256"] for found in connection.execute("SELECT sha256 FROM photos")
    }
    leftover = sorted(
        (path for paths in remaining_by_hash.values() for path in paths),
        key=lambda path: path.name.casefold(),
    )
    for path in leftover:
        info = read_image_info(path)
        if info is None or info.sha256 in known_hashes:
            continue
        max_sequence += 1
        insert_photo_row(
            connection,
            photo_id=str(uuid.uuid4()),
            case_id=case_id,
            role=role_from_filename(path.name) or "其他",
            sequence=max_sequence,
            original_name=path.name,
            stored_name=path.name,
            stored_path=(Path(folder_path) / path.name).as_posix(),
            sha256=info.sha256,
            size_bytes=info.size_bytes,
            width=info.width,
            height=info.height,
        )
        known_hashes.add(info.sha256)
        counts["photos_added"] += 1

    if prune:
        for row in missing_rows:
            connection.execute("DELETE FROM photos WHERE id = ?", (row["id"],))
            counts["photos_removed"] += 1

    if any(counts.values()):
        connection.execute(
            "UPDATE cases SET photo_count = (SELECT COUNT(*) FROM photos WHERE case_id = ?) "
            "WHERE id = ?",
            (case_id, case_id),
        )
    return counts
