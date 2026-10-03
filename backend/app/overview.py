# ruff: noqa: E501
"""照片總覽：依材料／棟別列出案件與照片，並可輸出為獨立網頁。

資料來源有兩種：
- db：以資料庫已登錄案件為準。
- disk：直接掃描磁碟資料夾，標題由資料夾名稱解析。
本模組只讀取照片，不修改、搬移或刪除任何檔案。
"""

from __future__ import annotations

import base64
import html
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .db import connect
from .schemas import CaseCreate
from .storage.errors import StorageError
from .storage.rescan import _case_from_folder, _fallback_case_from_folder

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
THUMB_SIZE = 360
LARGE_SIZE = 1000


@dataclass
class OverviewPhoto:
    name: str
    path: Path
    role: str = ""
    photo_id: str = ""


@dataclass
class OverviewCase:
    title: str
    work_date: str
    material: str
    building: str
    folder: Path
    case_id: str = ""
    issues: list[str] = field(default_factory=list)
    photos: list[OverviewPhoto] = field(default_factory=list)


def case_title(building: str, floor: str, address_code: str, issues: list[str]) -> str:
    """與案件資料夾名稱相同的規則：棟別與樓層連寫，其餘以空白分隔。"""
    return f"{building}{floor} {address_code} {'-'.join(issues)}"


def collect_from_database(
    database_path: Path, *, material: str = "", building: str = ""
) -> list[OverviewCase]:
    clauses: list[str] = []
    parameters: list[str] = []
    if material:
        clauses.append("material = ?")
        parameters.append(material)
    if building:
        clauses.append("building = ?")
        parameters.append(building)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cases: list[OverviewCase] = []
    with connect(database_path) as connection:
        rows = connection.execute(
            f"SELECT * FROM cases {where} ORDER BY work_date DESC, created_at DESC",
            parameters,
        ).fetchall()
        for row in rows:
            issues = json.loads(row["issues_json"])
            root = Path(row["storage_root"]).resolve() if row["storage_root"] else Path()
            folder = (root / row["folder_path"]).resolve()
            photo_rows = connection.execute(
                "SELECT id, role, stored_name, stored_path FROM photos "
                "WHERE case_id = ? ORDER BY sequence",
                (row["id"],),
            ).fetchall()
            cases.append(
                OverviewCase(
                    title=case_title(row["building"], row["floor"], row["address_code"], issues),
                    work_date=row["work_date"],
                    material=row["material"],
                    building=row["building"],
                    folder=folder,
                    case_id=row["id"],
                    issues=issues,
                    photos=[
                        OverviewPhoto(
                            name=photo["stored_name"],
                            path=(root / photo["stored_path"]).resolve(),
                            role=photo["role"],
                            photo_id=photo["id"],
                        )
                        for photo in photo_rows
                    ],
                )
            )
    return cases


def _images_in(folder: Path) -> list[Path]:
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    return sorted(
        (
            path
            for path in entries
            if path.suffix.casefold() in IMAGE_EXTENSIONS and path.is_file()
        ),
        key=lambda path: path.name.casefold(),
    )


def collect_from_disk(
    root: Path, *, material: str = "", building: str = ""
) -> list[OverviewCase]:
    root = root.resolve()
    if not root.is_dir():
        raise StorageError("掃描路徑不存在或不是資料夾")
    cases: list[OverviewCase] = []
    for current, directory_names, _ in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            (name for name in directory_names if not name.startswith(".")),
            key=str.casefold,
        )
        folder = Path(current)
        if folder == root:
            continue
        images = _images_in(folder)
        if not images:
            continue
        parsed: CaseCreate | None = _case_from_folder(folder)
        if parsed is not None:
            title = case_title(parsed.building, parsed.floor, parsed.address_code, parsed.issues)
            case_building, issues, work_date = parsed.building, parsed.issues, parsed.work_date.isoformat()
        else:
            fallback = _fallback_case_from_folder(folder)
            title = folder.name
            case_building = fallback.building if fallback else "未辨識"
            issues = []
            work_date = fallback.work_date.isoformat() if fallback else ""
        case_material = folder.parent.name
        if (material and case_material != material) or (building and case_building != building):
            continue
        cases.append(
            OverviewCase(
                title=title,
                work_date=work_date,
                material=case_material,
                building=case_building,
                folder=folder,
                issues=issues,
                photos=[OverviewPhoto(name=path.name, path=path) for path in images],
            )
        )
    cases.sort(key=lambda item: (item.work_date, item.title), reverse=True)
    return cases


def make_image_bytes(path: Path, max_side: int, quality: int = 78) -> bytes:
    """產生縮圖 JPEG（依 EXIF 轉正）。原檔不受影響。"""
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((max_side, max_side))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
    except (OSError, UnidentifiedImageError) as error:
        raise StorageError(f"無法讀取圖片：{path.name}") from error
    return buffer.getvalue()


def _data_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def filename_groups(cases: list[OverviewCase]) -> str:
    """依案件分組的檔名清單，不去除重複。"""
    blocks = [
        "\n".join([case.title, *(photo.name for photo in case.photos)]) for case in cases
    ]
    return "\n\n".join(blocks)


def render_html(
    cases: list[OverviewCase], *, material: str, building: str, mode: str
) -> str:
    """輸出單一 HTML。light：縮圖內嵌、放大看原檔路徑；standalone：縮圖與放大圖皆內嵌。"""
    label = " · ".join(part for part in (building, material) if part) or "全部"
    sections: list[str] = []
    for case in cases:
        figures: list[str] = []
        for photo in case.photos:
            try:
                thumb = _data_uri(make_image_bytes(photo.path, THUMB_SIZE, 72))
                full = (
                    _data_uri(make_image_bytes(photo.path, LARGE_SIZE, 70))
                    if mode == "standalone"
                    else photo.path.as_uri()
                )
            except StorageError:
                continue
            figures.append(
                f'<figure><img src="{thumb}" data-full="{html.escape(full, quote=True)}" '
                f'alt="{html.escape(photo.name)}" loading="lazy">'
                f"<figcaption>{html.escape(photo.name)}</figcaption></figure>"
            )
        sections.append(
            f'<section class="case"><h2>{html.escape(case.title)}'
            f"<small>{html.escape(case.work_date)}</small></h2>"
            f'<div class="row">{"".join(figures)}</div></section>'
        )
    names = html.escape(filename_groups(cases))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note = "獨立版（可直接傳給他人）" if mode == "standalone" else "輕量版（放大檢視讀取本機原始照片）"
    return _HTML.format(
        label=html.escape(label),
        total=len(cases),
        stamp=stamp,
        note=note,
        body="".join(sections) or '<p class="empty">沒有符合條件的案件。</p>',
        names=names,
        thumb=THUMB_SIZE // 2,
    )


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatLens 照片總覽 {label}</title>
<style>
body{{margin:0;font-family:"Microsoft JhengHei",system-ui,sans-serif;background:#f4f6f8;color:#1c2630}}
header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #d5dbe1;padding:12px 20px;display:flex;flex-wrap:wrap;gap:14px;align-items:center;z-index:2}}
header h1{{margin:0;font-size:20px}} header small{{color:#6b7782}}
main{{padding:16px 20px}} .case{{background:#fff;border:1px solid #d5dbe1;border-radius:8px;padding:12px 14px;margin-bottom:14px}}
.case h2{{margin:0 0 8px;font-size:16px}} .case h2 small{{margin-left:10px;color:#6b7782;font-weight:400;font-size:12px}}
.row{{display:flex;flex-wrap:wrap;gap:10px}} figure{{margin:0;width:var(--w,{thumb}px)}}
figure img{{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:4px;cursor:zoom-in;background:#e6eaee}}
figcaption{{font-size:12px;margin-top:3px;word-break:break-all;color:#44525e}}
button,input{{font:inherit}} button{{padding:5px 12px;border:1px solid #9aa7b2;border-radius:5px;background:#fff;cursor:pointer}}
dialog{{border:0;border-radius:8px;padding:0;max-width:92vw}} dialog textarea{{width:min(640px,86vw);height:60vh;border:0;padding:12px;font:14px/1.5 Consolas,monospace}}
#lb{{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:9}}
#lb img{{max-width:94vw;max-height:90vh}} #lb.on{{display:flex}} .empty{{color:#6b7782}}
</style></head><body>
<header><h1>{label}共 {total} 筆</h1>
<label>縮圖大小 <input id="size" type="range" min="90" max="360" value="{thumb}"></label>
<button id="names-btn" type="button">檔名清單</button>
<small>{note}　產生時間 {stamp}</small></header>
<main>{body}</main>
<dialog id="names"><textarea id="names-text" readonly>{names}</textarea>
<div style="padding:8px;text-align:right"><button id="copy" type="button">全部複製</button> <button id="close" type="button">關閉</button></div></dialog>
<div id="lb"><img alt=""></div>
<script>
const $=s=>document.querySelector(s), imgs=[...document.querySelectorAll('figure img')];
$('#size').oninput=e=>document.documentElement.style.setProperty('--w',e.target.value+'px');
$('#names-btn').onclick=()=>$('#names').showModal(); $('#close').onclick=()=>$('#names').close();
$('#copy').onclick=async()=>{{const t=$('#names-text');t.select();try{{await navigator.clipboard.writeText(t.value)}}catch(e){{document.execCommand('copy')}}$('#copy').textContent='已複製'}};
let cur=-1; const lb=$('#lb');
function show(i){{if(i<0||i>=imgs.length)return;cur=i;lb.querySelector('img').src=imgs[i].dataset.full;lb.classList.add('on')}}
imgs.forEach((im,i)=>im.onclick=()=>show(i)); lb.onclick=()=>lb.classList.remove('on');
document.onkeydown=e=>{{if(!lb.classList.contains('on'))return;if(e.key==='Escape')lb.classList.remove('on');if(e.key==='ArrowRight')show(cur+1);if(e.key==='ArrowLeft')show(cur-1)}};
</script></body></html>
"""
