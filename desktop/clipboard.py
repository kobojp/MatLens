"""Read clipboard images on explicit user action; never change source files."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageGrab

from backend.app.config import MAX_PHOTO_BYTES

MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def read_images() -> dict:
    try:
        content = ImageGrab.grabclipboard()
        images = []
        if isinstance(content, Image.Image):
            if Image.MAX_IMAGE_PIXELS and content.width * content.height > Image.MAX_IMAGE_PIXELS:
                return {"error": "剪貼簿圖片尺寸過大，請縮小後再貼上。"}
            output = io.BytesIO()
            content.save(output, format="PNG")
            raw = output.getvalue()
            if len(raw) > MAX_PHOTO_BYTES:
                return {"error": "單張圖片不可超過 25 MiB。"}
            images.append({"name": "貼上圖片.png", "mime": "image/png",
                           "data": base64.b64encode(raw).decode("ascii")})
        elif isinstance(content, list):
            if len(content) > 30:
                return {"error": "單次貼上最多 30 張照片。"}
            total = 0
            for filename in dict.fromkeys(content):
                path = Path(filename)
                if (not path.is_absolute()
                        or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}
                        or not path.is_file()):
                    continue
                with path.open("rb") as source:
                    raw = source.read(MAX_PHOTO_BYTES + 1)
                if len(raw) > MAX_PHOTO_BYTES:
                    return {"error": "單張圖片不可超過 25 MiB。"}
                total += len(raw)
                if total > 75 * 1024 * 1024:
                    return {"error": "一次貼上圖片總大小不可超過 75 MiB，請分批貼上。"}
                with Image.open(io.BytesIO(raw)) as picture:
                    mime = MIME.get(picture.format)
                    picture.verify()
                if mime:
                    images.append({"name": path.name, "mime": mime,
                                   "data": base64.b64encode(raw).decode("ascii")})
        if not images:
            return {"error": "剪貼簿沒有可貼上的圖片，請使用「複製圖片」後再試。"}
        return {"images": images}
    except (OSError, ValueError, Image.DecompressionBombError):
        return {"error": "無法讀取剪貼簿圖片，請重新複製圖片或改用匯入照片。"}
