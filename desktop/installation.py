"""Known per-user program locations; the data directory never moves."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def program_directories() -> tuple[Path, Path]:
    local = Path(os.environ["LOCALAPPDATA"])
    return local / "MatLens" / "app", local / "Programs" / "MatLens"


def validate_program_directory(path: Path) -> Path:
    target = path.absolute()
    if target not in program_directories() or target.resolve() != target:
        raise ValueError("安裝位置不正確，停止更新。")
    if (target / "MatLens.exe").resolve().parent != target:
        raise ValueError("程式路徑不可重新導向。")
    return target


def running_installation() -> tuple[Path | None, str]:
    if not getattr(sys, "frozen", False):
        return None, "development"
    if Path(sys.executable).name.casefold() != "matlens.exe":
        return None, "portable"
    try:
        target = validate_program_directory(Path(sys.executable).parent)
    except ValueError:
        return None, "portable"
    return target, "installed" if target == program_directories()[0] else "legacy"
