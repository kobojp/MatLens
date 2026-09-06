from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import (
    BUILDINGS,
    DATABASE_PATH,
    FRONTEND_DIST,
    ISSUES,
    MATERIALS,
    PHOTO_ROLES,
    PHOTO_ROOT,
)
from .db import connect, get_setting, initialize, set_setting
from .schemas import CaseCreate, CustomOptionCreate, StorageSettingsUpdate
from .storage import (
    DuplicatePhotoError,
    StorageError,
    create_case,
    get_case,
    list_cases,
)


def create_app(
    *,
    database_path: Path = DATABASE_PATH,
    photo_root: Path = PHOTO_ROOT,
    frontend_dist: Path = FRONTEND_DIST,
    folder_picker: Callable[[str], str | None] | None = None,
) -> FastAPI:
    initialize(database_path)
    photo_root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="MatLens API", version="0.1.0")
    app.state.database_path = database_path
    app.state.photo_root = photo_root
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/reference-values")
    def reference_values() -> dict[str, list[str]]:
        with connect(app.state.database_path) as connection:
            custom_rows = connection.execute(
                "SELECT option_type, value FROM custom_options ORDER BY id"
            ).fetchall()
        custom_materials = [
            row["value"] for row in custom_rows if row["option_type"] == "material"
        ]
        custom_issues = [
            row["value"] for row in custom_rows if row["option_type"] == "issue"
        ]
        return {
            "buildings": BUILDINGS,
            "materials": [*MATERIALS, *custom_materials],
            "issues": [*ISSUES, *custom_issues],
            "photo_roles": PHOTO_ROLES,
            "custom_materials": custom_materials,
            "custom_issues": custom_issues,
        }

    @app.post("/api/reference-values/{option_type}", status_code=201)
    def add_reference_value(
        option_type: Literal["material", "issue"],
        option: CustomOptionCreate,
    ) -> dict[str, str]:
        defaults = MATERIALS if option_type == "material" else ISSUES
        if option.value.casefold() in {value.casefold() for value in defaults}:
            raise HTTPException(status_code=409, detail="此選項已存在")
        try:
            with connect(app.state.database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO custom_options (option_type, value, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (option_type, option.value, datetime.now(UTC).isoformat()),
                )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise HTTPException(status_code=409, detail="此選項已存在") from error
            raise
        return {"type": option_type, "value": option.value}

    @app.delete("/api/reference-values/{option_type}")
    def delete_reference_value(
        option_type: Literal["material", "issue"],
        option: CustomOptionCreate,
    ) -> dict[str, str]:
        with connect(app.state.database_path) as connection:
            result = connection.execute(
                "DELETE FROM custom_options WHERE option_type = ? AND value = ?",
                (option_type, option.value),
            )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="只能刪除自訂選項")
        return {"type": option_type, "value": option.value}

    def active_storage_root() -> Path:
        configured = get_setting(
            app.state.database_path,
            "storage_root",
            str(app.state.photo_root),
        )
        return Path(configured).resolve()

    def configure_storage_root(path_value: str) -> Path:
        target = Path(path_value.strip()).expanduser()
        if not target.is_absolute():
            raise HTTPException(status_code=422, detail="儲存目錄必須使用完整路徑")
        try:
            target.mkdir(parents=True, exist_ok=True)
            target = target.resolve()
            probe = target / f".matlens-write-test-{uuid.uuid4()}"
            probe.write_text("MatLens", encoding="utf-8")
            probe.unlink()
        except OSError as error:
            raise HTTPException(status_code=400, detail="此目錄無法寫入") from error
        set_setting(app.state.database_path, "storage_root", str(target))
        return target

    @app.get("/api/settings/storage")
    def storage_settings() -> dict[str, str]:
        return {"path": str(active_storage_root())}

    @app.post("/api/settings/storage")
    def update_storage_settings(settings: StorageSettingsUpdate) -> dict[str, str]:
        return {"path": str(configure_storage_root(settings.path))}

    @app.post("/api/settings/storage/pick-folder")
    def pick_storage_folder() -> dict[str, object]:
        if folder_picker is not None:
            try:
                selected = folder_picker(str(active_storage_root()))
            except Exception as error:
                raise HTTPException(status_code=500, detail="無法開啟資料夾選擇器") from error
            if not selected:
                return {"path": str(active_storage_root()), "cancelled": True}
            return {"path": str(configure_storage_root(selected)), "cancelled": False}
        if os.name != "nt":
            raise HTTPException(status_code=501, detail="資料夾選擇器僅支援 Windows")
        environment = os.environ.copy()
        environment["MATLENS_PICKER_INITIAL"] = str(active_storage_root())
        script = """
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '選擇 MatLens 照片儲存目錄'
$dialog.ShowNewFolderButton = $true
if (Test-Path -LiteralPath $env:MATLENS_PICKER_INITIAL) {
    $dialog.SelectedPath = $env:MATLENS_PICKER_INITIAL
}
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
}
"""
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                timeout=600,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HTTPException(status_code=500, detail="無法開啟資料夾選擇器") from error
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="資料夾選擇器執行失敗")
        selected = result.stdout.strip()
        if not selected:
            return {"path": str(active_storage_root()), "cancelled": True}
        return {"path": str(configure_storage_root(selected)), "cancelled": False}

    @app.get("/api/cases")
    def cases_index(
        q: str = Query(default="", max_length=100),
        building: str = Query(default="", max_length=40),
        material: str = Query(default="", max_length=40),
    ) -> dict[str, object]:
        items = list_cases(
            app.state.database_path,
            query=q.strip(),
            building=building.strip(),
            material=material.strip(),
        )
        return {"items": items, "total": len(items)}

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str) -> dict[str, object]:
        try:
            return get_case(app.state.database_path, case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到案件") from error

    @app.post("/api/cases", status_code=201)
    async def case_create(
        work_date: str = Form(...),
        building: str = Form(...),
        floor: str = Form(...),
        address_code: str = Form(...),
        material: str = Form(...),
        issues: str = Form(...),
        location: str = Form(default=""),
        notes: str = Form(default=""),
        photo_roles: str = Form(...),
        photos: list[UploadFile] = File(...),
    ) -> dict[str, object]:
        try:
            parsed_issues = json.loads(issues)
            parsed_roles = json.loads(photo_roles)
            if not isinstance(parsed_issues, list) or not isinstance(parsed_roles, list):
                raise ValueError
            case = CaseCreate(
                work_date=work_date,
                building=building,
                floor=floor,
                address_code=address_code,
                material=material,
                issues=parsed_issues,
                location=location,
                notes=notes,
            )
        except (json.JSONDecodeError, ValueError, ValidationError) as error:
            raise HTTPException(status_code=422, detail="案件欄位格式不正確") from error

        try:
            return await create_case(
                database_path=app.state.database_path,
                photo_root=active_storage_root(),
                case=case,
                uploads=photos,
                roles=[str(role) for role in parsed_roles],
            )
        except DuplicatePhotoError as error:
            raise HTTPException(
                status_code=409,
                detail={"message": "發現重複照片，案件尚未儲存", "duplicates": error.duplicates},
            ) from error
        except StorageError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/photos/{photo_id}/content")
    def photo_content(photo_id: str) -> FileResponse:
        with connect(app.state.database_path) as connection:
            row = connection.execute(
                """
                SELECT photos.stored_path, cases.storage_root
                FROM photos
                JOIN cases ON cases.id = photos.case_id
                WHERE photos.id = ?
                """,
                (photo_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到照片")
        case_root = Path(row["storage_root"] or app.state.photo_root).resolve()
        target = (case_root / row["stored_path"]).resolve()
        if case_root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="照片檔案不存在")
        return FileResponse(target)

    @app.post("/api/cases/{case_id}/open-folder", status_code=204)
    def open_case_folder(case_id: str) -> None:
        try:
            case = get_case(app.state.database_path, case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到案件") from error
        case_root = Path(str(case["storage_root"] or app.state.photo_root)).resolve()
        folder = (case_root / str(case["folder_path"])).resolve()
        if case_root not in folder.parents or not folder.is_dir():
            raise HTTPException(status_code=404, detail="案件資料夾不存在")
        if os.name != "nt":
            raise HTTPException(status_code=501, detail="此功能僅支援 Windows")
        os.startfile(folder)  # type: ignore[attr-defined]

    if frontend_dist.is_dir():
        assets = frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str = "") -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="找不到 API")
            requested = frontend_dist / path
            if (
                path
                and requested.is_file()
                and frontend_dist.resolve() in requested.resolve().parents
            ):
                return FileResponse(requested)
            return FileResponse(frontend_dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def development_hint() -> dict[str, str]:
            return {"message": "MatLens API 正在執行；前端尚未建置。"}

    return app


def __getattr__(name: str) -> FastAPI:
    # Keep main:app compatible without creating a database when importing the factory.
    if name == "app":
        instance = create_app()
        globals()[name] = instance
        return instance
    raise AttributeError(name)
