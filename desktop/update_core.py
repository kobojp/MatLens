"""Signed metadata, bounded HTTPS downloads and safe Windows ZIP extraction."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import stat
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from desktop.version import DATA_COMPATIBILITY

MAX_PACKAGE = 512 * 1024 * 1024


def https_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("更新來源必須使用 HTTPS，且不可包含帳號密碼。")
    return url


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, https_url(newurl))


def download(url: str, target: Path, limit: int, progress=lambda count: None) -> None:
    request = urllib.request.Request(https_url(url), headers={
        "User-Agent": "MatLens-Updater", "Cache-Control": "no-cache",
    })
    opener = urllib.request.build_opener(HTTPSRedirect())
    deadline = time.monotonic() + 600
    with opener.open(request, timeout=20) as response, target.open("xb") as output:
        https_url(response.geturl())
        count = 0
        while chunk := response.read(128 * 1024):
            count += len(chunk)
            if count > limit or time.monotonic() > deadline:
                raise ValueError("更新下載超過大小或時間限制，請重試。")
            output.write(chunk)
            progress(count)


def version_key(value: str) -> tuple[int, int, int, int, int]:
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-rc\.(\d+))?", value)
    if not match:
        raise ValueError("更新版本格式不正確。")
    major, minor, patch, rc = match.groups()
    return int(major), int(minor), int(patch), int(rc is None), int(rc or 0)


def verify_manifest(raw: bytes, public_key: str, channel: str) -> dict:
    try:
        envelope = json.loads(raw)
        payload = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            signature, payload,
        )
        value = json.loads(payload)
        version_key(value["version"])
        if value["channel"] != channel or channel not in {"stable", "preview"}:
            raise ValueError("channel")
        if channel == "stable" and "-" in value["version"]:
            raise ValueError("prerelease")
        if value["platform"] != "win-x64" or value["data_compatibility"] != DATA_COMPATIBILITY:
            raise ValueError("compatibility")
        if not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
            raise ValueError("digest")
        if type(value["size"]) is not int or not 0 < value["size"] <= MAX_PACKAGE:
            raise ValueError("size")
        if not isinstance(value["notes"], str) or len(value["notes"]) > 20000:
            raise ValueError("notes")
        https_url(value["url"])
        return value
    except Exception as error:
        raise ValueError("更新簽章或資訊驗證失敗，已停止更新。") from error


def verify_package(path: Path, manifest: dict) -> None:
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if path.stat().st_size != manifest["size"] or digest != manifest["sha256"]:
        raise ValueError("更新包不完整或已遭修改，請重新下載。")


def extract_package(package: Path, destination: Path) -> Path:
    """Validate all members before writing; never use extractall on an untrusted ZIP."""
    reserved = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
    with zipfile.ZipFile(package) as archive:
        entries = archive.infolist()
        if len(entries) > 15000 or sum(item.file_size for item in entries) > 2 * 1024**3:
            raise ValueError("更新包解壓縮大小超出限制。")
        seen = set()
        for item in entries:
            name = item.filename.replace("\\", "/").rstrip("/")
            parts = name.split("/")
            if (not parts or parts[0] != "MatLens" or any(
                part in {"", ".", ".."} or part.endswith((" ", "."))
                or re.search(r'[<>:"|?*\x00-\x1f]', part) or reserved.match(part)
                for part in parts
            ) or stat.S_ISLNK(item.external_attr >> 16) or name.casefold() in seen):
                raise ValueError("更新包包含不安全或重複的檔案路徑。")
            seen.add(name.casefold())
        if "matlens/matlens.exe" not in seen or "matlens/matlensupdater.exe" not in seen:
            raise ValueError("更新包缺少主程式或更新器。")
        destination.mkdir(parents=True, exist_ok=False)
        for item in entries:
            target = destination.joinpath(*item.filename.replace("\\", "/").rstrip("/").split("/"))
            if item.is_dir() or item.filename.endswith("\\"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as output:
                    while chunk := source.read(128 * 1024):
                        output.write(chunk)
    return destination / "MatLens"
