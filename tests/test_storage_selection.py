from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db import get_setting, set_setting
from backend.app.main import create_app
from tests.test_api import create_case


def make_client(root: Path) -> TestClient:
    return TestClient(create_app(database_path=root / "app.db", photo_root=root / "photos"))


def test_storage_selection_persists_in_sqlite_and_keeps_old_roots(tmp_path):
    client = make_client(tmp_path)
    root = tmp_path / "現場照片"
    (root / "底座").mkdir(parents=True)
    original = root / "底座/original.jpg"
    original.write_bytes(b"original")
    value = {"path": str(root), "subfolder": "底座", "with_date": False}
    response = client.post("/api/settings/storage-selection", json=value)
    assert response.status_code == 200
    expected = {**value, "path": str(root.resolve())}
    assert response.json() == expected
    assert make_client(tmp_path).get("/api/settings/storage-selection").json() == expected
    assert json.loads(get_setting(tmp_path / "app.db", "storage_selection")) == expected
    assert client.get("/api/settings/storage").json()["path"] == str(root.resolve())
    assert original.read_bytes() == b"original"


def test_storage_selection_loads_legacy_path_without_writing_defaults(tmp_path):
    client = make_client(tmp_path)
    missing = tmp_path / "離線磁碟"
    set_setting(tmp_path / "app.db", "free_scan_path", str(missing))
    assert client.get("/api/settings/storage-selection").json() == {
        "path": str(missing.resolve()), "subfolder": "", "with_date": True,
    }
    assert not missing.exists()
    assert get_setting(tmp_path / "app.db", "storage_selection") == ""


@pytest.mark.parametrize("subfolder", ["../outside", "..", "missing", "底座/其他"])
def test_invalid_selection_does_not_overwrite_saved_settings(tmp_path, subfolder):
    client = make_client(tmp_path)
    root = tmp_path / "現場"
    (root / "底座").mkdir(parents=True)
    good = {"path": str(root), "subfolder": "底座", "with_date": True}
    assert client.post("/api/settings/storage-selection", json=good).status_code == 200
    response = client.post("/api/settings/storage-selection", json={**good, "subfolder": subfolder})
    assert response.status_code in {400, 422}
    assert client.get("/api/settings/storage-selection").json()["subfolder"] == "底座"


def test_selection_rejects_relative_missing_path_and_non_boolean(tmp_path):
    client = make_client(tmp_path)
    for value in [
        {"path": "relative", "subfolder": "", "with_date": True},
        {"path": str(tmp_path / "missing"), "subfolder": "", "with_date": True},
        {"path": str(tmp_path), "subfolder": "", "with_date": "false"},
    ]:
        assert client.post("/api/settings/storage-selection", json=value).status_code in {400, 422}
    assert not (tmp_path / "missing").exists()


def test_folder_picker_can_validate_without_changing_saved_root(tmp_path):
    chosen = tmp_path / "選擇位置"
    chosen.mkdir()
    app = create_app(database_path=tmp_path / "app.db", photo_root=tmp_path / "photos",
                     folder_picker=lambda initial: str(chosen))
    client = TestClient(app)
    before = client.get("/api/settings/storage").json()
    assert client.post("/api/settings/storage/pick-folder?persist=false").json() == {
        "path": str(chosen.resolve()), "cancelled": False,
    }
    assert client.get("/api/settings/storage").json() == before
    assert not list(chosen.iterdir())


def test_switching_selection_keeps_existing_month_case_and_original_photos(tmp_path):
    client = make_client(tmp_path)
    (tmp_path / "photos" / "8月" / "底座").mkdir(parents=True)
    response = create_case(client, [(10, 20, 30)], storage_month="8月")
    assert response.status_code == 201
    case = response.json()
    detail_url = f"/api/cases/{case['id']}"
    before = client.get(detail_url).json()
    photo_url = before["photos"][0]["content_url"]
    image = client.get(photo_url).content
    root = tmp_path / "新位置"
    (root / "磁力門扣").mkdir(parents=True)
    assert client.post("/api/settings/storage-selection", json={
        "path": str(root), "subfolder": "磁力門扣", "with_date": False,
    }).status_code == 200
    reopened = make_client(tmp_path)
    assert reopened.get(detail_url).json() == before
    assert reopened.get(photo_url).content == image
