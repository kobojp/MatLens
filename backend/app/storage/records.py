from __future__ import annotations

import json
import sqlite3

from ..schemas import CaseCreate


def insert_case_row(
    connection: sqlite3.Connection,
    *,
    case_id: str,
    case: CaseCreate,
    storage_root: str,
    folder_path: str,
    photo_count: int,
    created_at: str,
) -> None:
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
            storage_root,
            folder_path,
            photo_count,
            created_at,
        ),
    )


def insert_photo_row(
    connection: sqlite3.Connection,
    *,
    photo_id: str,
    case_id: str,
    role: str,
    sequence: int,
    original_name: str,
    stored_name: str,
    stored_path: str,
    sha256: str,
    size_bytes: int,
    width: int,
    height: int,
) -> None:
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
            original_name,
            stored_name,
            stored_path,
            sha256,
            size_bytes,
            width,
            height,
        ),
    )
