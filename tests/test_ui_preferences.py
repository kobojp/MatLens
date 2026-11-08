from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.db import get_setting, set_setting
from backend.app.main import create_app
from tests.test_api import create_case

DEFAULT = {"layout": "tiles", "panel_position": "right", "tile_size": "large",
           "panel_collapsed": False}


def client_at(root):
    return TestClient(create_app(database_path=root / "app.db", photo_root=root / "photos"))


def test_ui_defaults_are_read_only_and_preferences_survive_new_app(tmp_path):
    client = client_at(tmp_path)
    assert client.get("/api/settings/ui-preferences").json() == DEFAULT
    assert get_setting(tmp_path / "app.db", "ui_preferences") == ""
    selected = {"layout": "classic", "panel_position": "top", "tile_size": "medium",
                "panel_collapsed": True}
    assert client.post("/api/settings/ui-preferences", json=selected).json() == selected
    assert client_at(tmp_path).get("/api/settings/ui-preferences").json() == selected


@pytest.mark.parametrize("invalid", [
    {"layout": "unknown"}, {"panel_position": "left"}, {"tile_size": "small"},
    {"panel_collapsed": "false"}, {"storage_root": "unrelated"},
])
def test_invalid_preferences_never_replace_saved_selection(tmp_path, invalid):
    client = client_at(tmp_path)
    assert client.post("/api/settings/ui-preferences", json=DEFAULT).status_code == 200
    result = client.post("/api/settings/ui-preferences", json={**DEFAULT, **invalid})
    assert result.status_code == 422
    assert client.get("/api/settings/ui-preferences").json() == DEFAULT


def test_reset_only_changes_ui_settings_and_preserves_real_case_photos(tmp_path):
    client = client_at(tmp_path)
    (tmp_path / "photos/8月/底座").mkdir(parents=True)
    created = create_case(client, [(10, 20, 30)])
    assert created.status_code == 201
    case_url = f"/api/cases/{created.json()['id']}"
    before = client.get(case_url).json()
    photo_url = before["photos"][0]["content_url"]
    image = client.get(photo_url).content
    database = tmp_path / "app.db"
    preserved = {"storage_selection": json.dumps({"path": "offline", "subfolder": "底座"}),
                 "role_order": '["後", "前", "中"]', "name_sequence": "true"}
    for key, value in preserved.items():
        set_setting(database, key, value)
    added = client.post("/api/reference-values/material", json={"value": "保留材料"})
    assert added.status_code == 201
    changed = client.post("/api/settings/ui-preferences", json={**DEFAULT, "layout": "classic"})
    assert changed.status_code == 200
    assert client.post("/api/settings/ui-preferences", json=DEFAULT).status_code == 200
    assert all(get_setting(database, key) == value for key, value in preserved.items())
    assert client.get(case_url).json() == before
    assert client.get(photo_url).content == image
    assert "保留材料" in client.get("/api/reference-values").json()["materials"]


def test_corrupt_saved_ui_settings_show_readable_error(tmp_path):
    client = client_at(tmp_path)
    set_setting(tmp_path / "app.db", "ui_preferences", "invalid-json")
    result = client.get("/api/settings/ui-preferences")
    assert result.status_code == 500
    assert "介面設定" in result.json()["detail"]
