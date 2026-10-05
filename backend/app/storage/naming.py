from __future__ import annotations

import re
from collections import Counter, defaultdict

from ..config import PHOTO_ROLES
from .paths import sanitize_component

_ROLE_ALTERNATION = "|".join(re.escape(role) for role in PHOTO_ROLES)

# 嚴格格式：[序號_]角色[-編號].副檔名，例如 01_前-1.jpg、前.jpg、中-2.png
SCANNED_PHOTO_RE = re.compile(
    rf"^(?:(?P<sequence>\d+)_)?(?P<role>{_ROLE_ALTERNATION})(?:[-_ ]?\d+)?"
    r"\.(?:jpe?g|png|webp)$",
    re.IGNORECASE,
)


def stored_names(
    roles: list[str], extensions: list[str], *, with_sequence: bool
) -> list[str]:
    """儲存檔名。同角色多張依序為 前-1、前-2；with_sequence 時再加 01_ 前綴。"""
    totals = Counter(roles)
    seen: defaultdict[str, int] = defaultdict(int)
    names: list[str] = []
    for index, (role, extension) in enumerate(zip(roles, extensions, strict=True), start=1):
        seen[role] += 1
        role_name = role if totals[role] == 1 else f"{role}-{seen[role]}"
        stem = sanitize_component(role_name)
        prefix = f"{index:02d}_" if with_sequence else ""
        names.append(f"{prefix}{stem}{extension.lower()}")
    return names


def role_from_filename(filename: str) -> str:
    """從（可能被使用者改過的）檔名判斷角色；無法判斷回傳空字串。

    先套用嚴格格式；否則檔名中恰好含一個已知角色時採用該角色。
    """
    matched = SCANNED_PHOTO_RE.fullmatch(filename)
    if matched:
        return matched.group("role")
    stem = filename.rsplit(".", 1)[0]
    found = {role for role in PHOTO_ROLES if role in stem}
    return found.pop() if len(found) == 1 else ""


def role_rank(role: str) -> int:
    return PHOTO_ROLES.index(role) if role in PHOTO_ROLES else len(PHOTO_ROLES)
