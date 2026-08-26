from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("MATLENS_DATA_DIR", PROJECT_ROOT / "data")).resolve()
DATABASE_PATH = Path(
    os.getenv("MATLENS_DATABASE_PATH", DATA_DIR / "matlens.db")
).resolve()
PHOTO_ROOT = Path(os.getenv("MATLENS_PHOTO_ROOT", DATA_DIR / "photos")).resolve()
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

MAX_PHOTO_BYTES = 25 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

BUILDINGS = [
    "二門診",
    "三門診",
    "思源",
    "致德",
    "身障",
    "長青",
    "立體",
    "臨床",
    "醫護宿舍",
    "正子中心",
    "重粒子",
    "135職務官舍",
]
MATERIALS = ["底座", "探頭", "模組", "磁力門扣"]
ISSUES = ["錯誤設備", "無回應", "火警", "漏水", "自檢異常", "鏽蝕", "故障"]
PHOTO_ROLES = ["前", "中", "完成", "樓層", "位置", "設備標籤", "其他"]
