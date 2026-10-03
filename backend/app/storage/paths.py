from __future__ import annotations

import re
from pathlib import Path

from .errors import StorageError

INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}



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
