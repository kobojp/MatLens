from __future__ import annotations

import os
import socket
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.db import initialize
from backend.app.main import create_app
from desktop.bridge import DraftState, confirm_close
from desktop.data import migrate_legacy
from desktop.server import protect_app, running_server


def test_migration_preserves_original_and_is_idempotent(tmp_path: Path):
    source = tmp_path / "舊版" / "matlens.db"
    initialize(source)
    with closing(sqlite3.connect(source)) as db, db:
        db.execute("INSERT INTO custom_options VALUES (1, 'issue', '測試問題', '2026-09-06')")
        db.execute(
            """INSERT INTO cases VALUES (
            'old', '2026-09-06', '二門診', '3F', 'M3', '底座', '["漏水"]', '', '',
            '', '2026/09/old', 0, '2026-09-06')"""
        )
    destination = tmp_path / "桌面版" / "matlens.db"
    backup = migrate_legacy(source, destination)
    assert backup and backup.exists()
    with closing(sqlite3.connect(destination)) as db:
        assert db.execute("SELECT storage_root FROM cases").fetchone()[0] == str(
            (source.parent / "photos").resolve()
        )
        assert db.execute("SELECT value FROM custom_options").fetchone()[0] == "測試問題"
    with closing(sqlite3.connect(source)) as db:
        assert db.execute("SELECT storage_root FROM cases").fetchone()[0] == ""
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute("SELECT storage_root FROM cases").fetchone()[0] == ""
    assert migrate_legacy(source, destination) is None
    assert len(list(backup.parent.glob("legacy-*.db"))) == 1


def test_non_matlens_database_does_not_create_destination(tmp_path: Path):
    source = tmp_path / "unrelated.db"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE unrelated (id INTEGER)")
    target = tmp_path / "target" / "matlens.db"
    with pytest.raises(RuntimeError, match="不是 MatLens"):
        migrate_legacy(source, target)
    assert not target.exists()


@pytest.mark.parametrize("cancel", [False, True])
def test_native_folder_picker_is_persisted_or_cancelled(tmp_path: Path, cancel: bool):
    selected = tmp_path / "照片目錄"
    app = create_app(
        database_path=tmp_path / "matlens.db", photo_root=tmp_path / "photos",
        frontend_dist=tmp_path / "missing",
        folder_picker=lambda initial: None if cancel else str(selected),
    )
    with TestClient(app) as client:
        before = client.get("/api/settings/storage").json()
        result = client.post("/api/settings/storage/pick-folder").json()
        assert result["cancelled"] is cancel
        assert client.get("/api/settings/storage").json()["path"] == (
            before["path"] if cancel else str(selected.resolve())
        )


def test_desktop_rejects_untrusted_requests(tmp_path: Path):
    app = create_app(database_path=tmp_path / "app.db", photo_root=tmp_path / "photos")
    protect_app(app, "test-token", "http://testserver")
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 403
        assert client.get("/?desktop_token=wrong").status_code == 403
        login = client.get("/?desktop_token=test-token", follow_redirects=False)
        assert login.status_code == 303
        assert "HttpOnly" in login.headers["set-cookie"]
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/settings/storage/pick-folder", headers={
            "origin": "https://untrusted.example",
        }).status_code == 403
        assert client.get("/api/health", headers={"host": "untrusted.example"}).status_code == 403


def test_live_server_starts_and_releases_port(tmp_path: Path):
    app = create_app(database_path=tmp_path / "app.db", photo_root=tmp_path / "photos")
    with running_server(app) as url, httpx.Client(follow_redirects=True) as client:
        parts = urlsplit(url)
        assert parts.port != 8000
        assert client.get(url).status_code == 200
        assert client.get(f"http://127.0.0.1:{parts.port}/api/health").json() == {"status": "ok"}
    with socket.socket() as check:
        assert check.connect_ex(("127.0.0.1", parts.port)) != 0


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex")
def test_second_instance_signals_first_and_releases_handles(tmp_path: Path):
    from desktop.instance import SingleInstance

    first = SingleInstance(tmp_path)
    second = SingleInstance(tmp_path)
    try:
        assert not first.already_running
        assert second.already_running
        assert first.wait_activation()
    finally:
        second.close()
        first.close()
    third = SingleInstance(tmp_path)
    try:
        assert not third.already_running
    finally:
        third.close()


def test_close_guard_never_needs_webview_and_ignores_stale_updates():
    state = DraftState()
    assert confirm_close(state, lambda *_: pytest.fail("No draft: no dialog needed"))
    state.update_state(2, True, False)
    state.update_state(1, False, False)
    assert not confirm_close(state, lambda *_: False)
    assert confirm_close(state, lambda *_: True)
    state.update_state(3, True, True)
    assert not confirm_close(state, lambda *_: True)
    state.update_state(4, False, False)
    assert confirm_close(state, lambda *_: pytest.fail("Save complete: no dialog needed"))
