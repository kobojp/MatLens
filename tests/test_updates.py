from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
import zipfile
from contextlib import closing

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from desktop.bridge import DesktopBridge
from desktop.update_core import (
    extract_package,
    https_url,
    verify_manifest,
    verify_package,
    version_key,
)
from desktop.updater import backup_database, swap_program
from desktop.updates import UpdateService


def signed_manifest(**overrides):
    private = Ed25519PrivateKey.generate()
    value = {"version": "0.4.0", "channel": "stable", "platform": "win-x64",
             "data_compatibility": 1, "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest(),
             "url": "https://example.com/package.zip", "notes": "更新說明", **overrides}
    payload = json.dumps(value).encode()
    raw = json.dumps({"payload": base64.b64encode(payload).decode(),
                      "signature": base64.b64encode(private.sign(payload)).decode()}).encode()
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    return raw, public


def test_signed_manifest_and_package(tmp_path):
    raw, public = signed_manifest()
    manifest = verify_manifest(raw, public, "stable")
    package = tmp_path / "package.zip"
    package.write_bytes(b"abc")
    verify_package(package, manifest)
    package.write_bytes(b"abd")
    with pytest.raises(ValueError, match="遭修改"):
        verify_package(package, manifest)
    envelope = json.loads(raw)
    envelope["payload"] = base64.b64encode(b"tampered").decode()
    with pytest.raises(ValueError, match="簽章"):
        verify_manifest(json.dumps(envelope).encode(), public, "stable")
    with pytest.raises(ValueError, match="簽章"):
        verify_manifest(raw, signed_manifest()[1], "stable")


@pytest.mark.parametrize("override", [
    {"size": -1}, {"size": True}, {"size": 1024**3}, {"sha256": "bad"},
    {"version": "0.4"}, {"version": "0.4.0-rc.1"}, {"channel": "preview"},
    {"url": "http://example.com/a"}, {"platform": "linux"}, {"data_compatibility": 2},
])
def test_reject_invalid_metadata(override):
    raw, public = signed_manifest(**override)
    with pytest.raises(ValueError, match="驗證失敗"):
        verify_manifest(raw, public, "stable")


def test_semantic_version_order_and_preview_channel():
    assert version_key("0.10.0") > version_key("0.9.9")
    assert version_key("1.0.0") > version_key("1.0.0-rc.99")
    assert version_key("1.0.0-rc.10") > version_key("1.0.0-rc.2")
    raw, public = signed_manifest(version="0.4.0-rc.1", channel="preview")
    assert verify_manifest(raw, public, "preview")["version"] == "0.4.0-rc.1"


@pytest.mark.parametrize("url", ["http://example.com", "file:///C:/test", "https://u:p@host/a"])
def test_insecure_urls_rejected(url):
    with pytest.raises(ValueError):
        https_url(url)


def zip_package(path, extra=None):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("MatLens\\MatLens.exe", b"exe")
        archive.writestr("MatLens\\MatLensUpdater.exe", b"helper")
        archive.writestr("MatLens/_internal/example.dll", b"dll")
        if extra:
            archive.writestr(extra, b"unsafe")


@pytest.mark.parametrize("member", [
    "../escape.exe", "MatLens/../escape", "MatLens/C:/evil", "MatLens/CON.txt",
    "MatLens/evil ", "MatLens/evil.", "MatLens/matlens.exe", "MatLens/foo:stream",
    "/MatLens/evil", "MatLens//evil", "Other/exe",
])
def test_zip_traversal_aliases_and_duplicates_rejected_before_writing(tmp_path, member):
    package = tmp_path / "package.zip"
    zip_package(package, member)
    destination = tmp_path / "unpack"
    with pytest.raises(ValueError):
        extract_package(package, destination)
    assert not destination.exists()


def test_extract_windows_zip(tmp_path):
    package = tmp_path / "package.zip"
    zip_package(package)
    folder = extract_package(package, tmp_path / "unpack")
    assert (folder / "MatLens.exe").read_bytes() == b"exe"
    assert (folder / "_internal" / "example.dll").read_bytes() == b"dll"


@pytest.mark.parametrize("fail", [False, True])
def test_swap_and_rollback_preserve_both_versions_and_data(tmp_path, fail):
    old, new, previous = [tmp_path / name for name in ["MatLens", "next", "previous"]]
    for folder, text in [(old, "old"), (new, "new")]:
        folder.mkdir()
        (folder / "MatLens.exe").write_text(text)
    data = tmp_path / "photos"
    data.mkdir()
    (data / "original.jpg").write_bytes(b"original")

    def start(folder):
        assert (folder / "MatLens.exe").read_text() == "new"
        if fail:
            raise RuntimeError("failed startup")

    if fail:
        with pytest.raises(RuntimeError):
            swap_program(old, new, previous, start)
        assert (old / "MatLens.exe").read_text() == "old"
        assert (new / "MatLens.exe").read_text() == "new"
    else:
        swap_program(old, new, previous, start)
        assert (old / "MatLens.exe").read_text() == "new"
        assert (previous / "MatLens.exe").read_text() == "old"
    assert (data / "original.jpg").read_bytes() == b"original"


def test_real_sqlite_wal_backup_preserves_original(tmp_path):
    source, backup = tmp_path / "original.db", tmp_path / "backup.db"
    with closing(sqlite3.connect(source)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE cases (name TEXT)")
        db.execute("INSERT INTO cases VALUES ('原始案件')")
        db.commit()
        backup_database(source, backup)
        assert db.execute("SELECT name FROM cases").fetchone()[0] == "原始案件"
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute("SELECT name FROM cases").fetchone()[0] == "原始案件"


@pytest.mark.parametrize("dirty,saving", [(True, False), (False, True), (True, True)])
def test_native_guard_rejects_unsaved_or_saving_even_if_frontend_claims_clean(dirty, saving):
    bridge = DesktopBridge(None, lambda: pytest.fail("must not close"))
    bridge.update_state(1, dirty, saving)
    assert "error" in bridge.install_update(False, False)


def settled(service):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = service.status()
        if state["phase"] not in {"checking", "downloading"}:
            return state
        time.sleep(0.01)
    pytest.fail("update worker did not finish")


def test_update_service_check_download_and_recheck(tmp_path, monkeypatch):
    raw, public = signed_manifest()
    service = UpdateService(tmp_path)
    service._source = {"public_key": public, "stable": "https://example.com/stable.json"}
    service._state["installable"] = True
    calls = []

    def fetch(url, target, limit, progress=lambda count: None):
        calls.append(url)
        target.write_bytes(raw if target.name == "manifest.json" else b"abc")
        progress(3)

    monkeypatch.setattr("desktop.updates.download", fetch)
    service.check()
    assert settled(service)["phase"] == "available"
    assert len(calls) == 1  # Checking never downloads or installs automatically.
    service.fetch_package()
    assert settled(service)["phase"] == "ready"
    assert service.status()["progress"] == 100
    first = service._job_dir
    service.check()
    assert settled(service)["phase"] == "available"
    assert service._job_dir != first
    assert (first / "package.zip").read_bytes() == b"abc"


def test_update_service_offline_and_missing_source_leave_app_usable(tmp_path, monkeypatch):
    service = UpdateService(tmp_path)

    def offline(*args):
        raise OSError("network down")

    monkeypatch.setattr("desktop.updates.download", offline)
    service.check()
    assert settled(service)["phase"] == "error"
    assert "原版本仍可使用" in service.status()["message"]
    service._source = {}
    service.check()
    assert "尚未設定" in settled(service)["message"]


def test_update_service_rejects_corrupt_download_and_downgrade(tmp_path, monkeypatch):
    raw, public = signed_manifest()
    service = UpdateService(tmp_path)
    service._source = {"public_key": public, "stable": "https://example.com/stable.json"}
    service._state["installable"] = True

    def fetch(url, target, limit, progress=lambda count: None):
        target.write_bytes(raw if target.name == "manifest.json" else b"corrupt")

    monkeypatch.setattr("desktop.updates.download", fetch)
    service.check()
    settled(service)
    service.fetch_package()
    assert settled(service)["phase"] == "error"
    assert "error" in service.launch_installer()
    raw, public = signed_manifest(version="0.1.0")
    service._source["public_key"] = public
    service.check()
    assert settled(service)["phase"] == "current"


def test_download_size_limit_and_https_redirect(tmp_path, monkeypatch):
    import io

    from desktop.update_core import HTTPSRedirect, download

    class Response(io.BytesIO):
        def geturl(self):
            return "https://example.com/a.zip"

    class Opener:
        def open(self, request, timeout):
            return Response(b"too big")

    monkeypatch.setattr("desktop.update_core.urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ValueError, match="大小"):
        download("https://example.com/a.zip", tmp_path / "download", 3)
    with pytest.raises(ValueError, match="HTTPS"):
        HTTPSRedirect().redirect_request(None, None, 302, "", {}, "http://example.com/a")


def test_zip_symlink_rejected(tmp_path):
    path = tmp_path / "symlink.zip"
    zip_package(path)
    with zipfile.ZipFile(path, "a") as archive:
        info = zipfile.ZipInfo("MatLens/link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "../../outside")
    with pytest.raises(ValueError):
        extract_package(path, tmp_path / "unpacked")


def test_new_app_sees_result_written_after_startup_and_after_restart(tmp_path):
    service = UpdateService(tmp_path)
    assert "last_result" not in service.status()
    report = tmp_path / "updates" / "last-result.json"
    report.parent.mkdir()
    report.write_text(json.dumps({"ok": True, "message": "已更新至 0.3.0。"}), "utf-8")
    assert service.status()["last_result"]["ok"]
    assert UpdateService(tmp_path).status()["last_result"]["message"] == "已更新至 0.3.0。"
