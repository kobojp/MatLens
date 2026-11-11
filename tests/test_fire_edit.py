from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db import connect
from backend.app.main import create_app
from tests.test_api import jpeg_bytes


def client_at(tmp_path):
    return TestClient(
        create_app(database_path=tmp_path / "matlens.db", photo_root=tmp_path / "photos")
    )


def fire_case(client, tmp_path, **extra):
    root = tmp_path / "photos"
    (root / "底座").mkdir(parents=True, exist_ok=True)
    data = dict(
        work_date="2026-11-10",
        building="二門診",
        floor="1F",
        address_code="M3-01",
        material="底座",
        issues='["火警", "底座故障"]',
        photo_roles='["前"]',
        free_scan_root=str(root),
        storage_subfolder="底座",
        free_with_date="false",
    )
    data.update(extra)
    response = client.post(
        "/api/cases",
        data=data,
        files=[("photos", ("source.jpg", jpeg_bytes((9, 4, 8)), "image/jpeg"))],
    )
    assert response.status_code == 201, response.text
    return response.json()


def update_body(case, **extra):
    body = {
        key: case[key]
        for key in [
            "work_date",
            "building",
            "floor",
            "address_code",
            "material",
            "issues",
            "location",
            "notes",
        ]
    }
    body.update(
        token=case["edit_token"],
        apply_naming=False,
        include_material=True,
        include_date=False,
        confirm_managed=False,
    )
    body.update(extra)
    return body


def test_independent_fire_details_persist_and_protect_defaults(tmp_path):
    client = client_at(tmp_path)
    assert (
        client.post("/api/reference-values/fire-detail", json={"value": "線路短路"}).status_code
        == 201
    )
    refs = client_at(tmp_path).get("/api/reference-values").json()
    assert "線路短路" in refs["fire_details"] and "線路短路" not in refs["issues"]
    assert (
        client.post("/api/reference-values/fire-detail", json={"value": "線路短路"}).status_code
        == 409
    )
    assert (
        client.post("/api/reference-values/fire-detail", json={"value": "   "}).status_code == 422
    )
    assert (
        client.request(
            "DELETE", "/api/reference-values/fire-detail", json={"value": "無回應"}
        ).status_code
        == 404
    )
    assert (
        client.request(
            "DELETE", "/api/reference-values/fire-detail", json={"value": "線路短路"}
        ).status_code
        == 200
    )
    assert "線路短路" not in client_at(tmp_path).get("/api/reference-values").json()["fire_details"]


def test_legacy_fire_options_are_copied_once_not_moved(tmp_path):
    client = client_at(tmp_path)
    client.post("/api/reference-values/issue", json={"value": "底座故障"})
    with connect(tmp_path / "matlens.db") as db:
        db.execute("DROP TABLE fire_detail_options")
        db.execute("DELETE FROM settings WHERE key='fire_details_migrated'")
    client = client_at(tmp_path)
    refs = client.get("/api/reference-values").json()
    assert "底座故障" in refs["fire_details"] and "底座故障" in refs["issues"]
    client.request("DELETE", "/api/reference-values/fire-detail", json={"value": "底座故障"})
    refs = client_at(tmp_path).get("/api/reference-values").json()
    assert "底座故障" not in refs["fire_details"] and "底座故障" in refs["issues"]


def test_fire_naming_preference_and_explicit_creation_choice(tmp_path):
    client = client_at(tmp_path)
    assert client.get("/api/settings/fire-naming").json() == {"include_material": True}
    assert (
        client.post("/api/settings/fire-naming", json={"include_material": False}).status_code
        == 200
    )
    assert client_at(tmp_path).get("/api/settings/fire-naming").json() == {
        "include_material": False
    }
    assert (
        client.post("/api/settings/fire-naming", json={"include_material": "false"}).status_code
        == 422
    )
    case = fire_case(client, tmp_path, fire_include_material="false")
    assert Path(case["folder_path"]).name == "二門診1F M3-01 火警 底座故障"
    assert case["material"] == "底座" and case["issues"] == ["火警", "底座故障"]
    client.post("/api/cases/rescan", params={"path": str(tmp_path / "photos/底座"), "prune": False})
    assert client.get("/api/cases/" + case["id"]).json()["material"] == "底座"


def test_edit_same_case_rename_and_metadata_preserve_photos(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    original = tmp_path / "photos" / case["folder_path"]
    photo = original / case["photos"][0]["stored_name"]
    content = photo.read_bytes()
    edit = client.get("/api/cases/" + case["id"] + "/edit").json()
    body = update_body(edit, address_code="M3-02", apply_naming=True, include_material=False)
    preview = client.post("/api/cases/" + case["id"] + "/edit-preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["new_path"].endswith("二門診1F M3-02 火警 底座故障")
    response = client.put("/api/cases/" + case["id"], json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["id"] == case["id"] and saved["photo_count"] == 1
    assert saved["photos"][0]["id"] == case["photos"][0]["id"]
    assert not original.exists()
    assert (tmp_path / "photos" / saved["folder_path"] / photo.name).read_bytes() == content
    assert client.get(saved["photos"][0]["content_url"]).content == content
    assert client.get("/api/cases").json()["total"] == 1
    edit = client.get("/api/cases/" + case["id"] + "/edit").json()
    response = client.put("/api/cases/" + case["id"], json=update_body(edit, notes="更正備註"))
    assert response.status_code == 200 and response.json()["folder_path"] == saved["folder_path"]
    assert list((tmp_path / "backups").glob("before-case-edit-*.db"))


def test_edit_rejects_stale_content_collision_and_unsafe_root(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    url = "/api/cases/" + case["id"]
    edit = client.get(url + "/edit").json()
    folder = tmp_path / "photos" / case["folder_path"]
    collision = folder.with_name("二門診1F M3-02 底座 火警 底座故障")
    collision.mkdir()
    assert client.put(url, json=update_body(edit, address_code="M3-02")).status_code == 409
    (folder / "external.txt").write_text("external change")
    assert client.put(url, json=update_body(edit, notes="stale")).status_code == 409
    with connect(tmp_path / "matlens.db") as db:
        db.execute("UPDATE cases SET folder_path=? WHERE id=?", ("../outside", case["id"]))
    assert client.get(url + "/edit").status_code == 400


def test_edit_rollback_and_restart_recovery(tmp_path, monkeypatch):
    from backend.app.storage import editing

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    url = "/api/cases/" + case["id"]
    edit = client.get(url + "/edit").json()

    def fail(*args):
        raise OSError("injected write failure")

    monkeypatch.setattr(editing, "_write_case", fail)
    response = client.put(url, json=update_body(edit, address_code="M3-02"))
    assert response.status_code == 400
    assert (tmp_path / "photos" / case["folder_path"]).is_dir()
    assert client.get(url).json()["address_code"] == "M3-01"
    # Simulate a process interruption after directory rename but before SQLite commit.
    old = tmp_path / "photos" / case["folder_path"]
    new = old.with_name("interrupted-rename")
    journal = editing._journal(tmp_path / "matlens.db", case["id"], old, new)
    old.rename(new)
    client_at(tmp_path)
    assert old.exists() and not new.exists() and not journal.exists()


@pytest.mark.parametrize("text", ["火警-底座故障", "火警 底座故障", "火警 線路-A 短路"])
def test_scanner_accepts_old_and_new_fire_separator(tmp_path, text):
    from backend.app.storage.rescan import _case_from_folder

    folder = tmp_path / "底座" / ("二門診1F M3-01 " + text)
    folder.mkdir(parents=True)
    case = _case_from_folder(folder)
    assert case.issues == ["火警", text.removeprefix("火警").lstrip("- ")]


def test_legacy_edit_preserves_style_and_requires_source_ack(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    folder = tmp_path / "photos" / case["folder_path"]
    legacy = folder.with_name(folder.name.replace("火警 ", "火警-"))
    folder.rename(legacy)
    with connect(tmp_path / "matlens.db") as db:
        db.execute(
            "UPDATE cases SET app_managed=0,naming_json='',folder_path=? WHERE id=?",
            (legacy.relative_to(tmp_path / "photos").as_posix(), case["id"]),
        )
        db.execute(
            "UPDATE photos SET stored_path=? WHERE case_id=?",
            ((legacy.relative_to(tmp_path / "photos") / "前.jpg").as_posix(), case["id"]),
        )
    url = "/api/cases/" + case["id"]
    edit = client.get(url + "/edit").json()
    assert edit["requires_managed_confirmation"] is True
    assert client.put(url, json=update_body(edit, notes="保留原名")).status_code == 200
    assert legacy.exists()
    edit = client.get(url + "/edit").json()
    body = update_body(edit, address_code="M3-02")
    assert client.put(url, json=body).status_code == 409
    body["confirm_managed"] = True
    saved = client.put(url, json=body).json()
    assert "火警-底座故障" in saved["folder_path"]
    client.post("/api/cases/rescan", params={"path": str(tmp_path / "photos/底座"), "prune": False})
    detail = client.get(url).json()
    assert detail["notes"] == "保留原名" and detail["address_code"] == "M3-02"


def test_metadata_edit_does_not_follow_changed_default_root(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path, material="探頭", fire_include_material="false")
    client.post("/api/settings/storage", json={"path": str(tmp_path / "elsewhere")})
    edit = client.get("/api/cases/" + case["id"] + "/edit").json()
    saved = client.put("/api/cases/" + case["id"], json=update_body(edit, notes="只改備註")).json()
    assert saved["storage_root"] == case["storage_root"]
    assert saved["folder_path"] == case["folder_path"]
    assert saved["material"] == "探頭"
    client.post("/api/cases/rescan", params={"path": str(tmp_path / "photos/底座"), "prune": False})
    assert client.get("/api/cases/" + case["id"]).json()["material"] == "探頭"


def test_permission_error_keeps_original_case(tmp_path, monkeypatch):
    from backend.app.storage import editing

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    url = "/api/cases/" + case["id"]
    edit = client.get(url + "/edit").json()
    original = editing.Path.rename

    def deny(self, target):
        if self.name.endswith("火警 底座故障"):
            raise PermissionError("test-only denied")
        return original(self, target)

    monkeypatch.setattr(editing.Path, "rename", deny)
    response = client.put(url, json=update_body(edit, address_code="M3-02"))
    assert response.status_code == 400
    assert client.get(url).json()["folder_path"] == case["folder_path"]
    assert (tmp_path / "photos" / case["folder_path"]).is_dir()


def test_committed_rename_recovery_and_external_conflict(tmp_path):
    from backend.app.storage import editing

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    root = tmp_path / "photos"
    old = root / case["folder_path"]
    new = old.with_name("committed-name")
    journal = editing._journal(tmp_path / "matlens.db", case["id"], old, new)
    old.rename(new)
    with connect(tmp_path / "matlens.db") as db:
        db.execute(
            "UPDATE cases SET folder_path=? WHERE id=?",
            (new.relative_to(root).as_posix(), case["id"]),
        )
        db.execute(
            "UPDATE photos SET stored_path=? WHERE case_id=?",
            ((new.relative_to(root) / "前.jpg").as_posix(), case["id"]),
        )
    client_at(tmp_path)
    assert new.exists() and not old.exists() and not journal.exists()
    journal = editing._journal(tmp_path / "matlens.db", case["id"], new, old)
    new.rename(old)
    (old / "external.txt").write_text("do not guess")
    with pytest.raises(Exception, match="內容已變更"):
        client_at(tmp_path)
    assert journal.exists() and old.exists()


def test_recovery_does_not_guess_when_both_paths_exist(tmp_path):
    from backend.app.storage import editing

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    old = tmp_path / "photos" / case["folder_path"]
    new = old.with_name("renamed-before-crash")
    journal = editing._journal(tmp_path / "matlens.db", case["id"], old, new)
    old.rename(new)
    old.mkdir()  # External program recreated the former path after interruption.
    with pytest.raises(Exception, match="兩個"):
        client_at(tmp_path)
    assert journal.exists() and old.exists() and new.exists()


@pytest.mark.parametrize("value", ["火警", "壞/路徑", "", " ", "x" * 41])
def test_invalid_fire_detail_does_not_modify_options(tmp_path, value):
    client = client_at(tmp_path)
    before = client.get("/api/reference-values").json()["fire_details"]
    assert (
        client.post("/api/reference-values/fire-detail", json={"value": value}).status_code == 422
    )
    assert client.get("/api/reference-values").json()["fire_details"] == before


def test_ambiguous_material_and_fire_words_are_not_guessed(tmp_path):
    from backend.app.storage.rescan import _case_from_folder

    folder = tmp_path / "底座" / "二門診1F M3-01 底座 火警 故障"
    folder.mkdir(parents=True)
    assert _case_from_folder(folder, material_names=["底座 火警"]) is None


def test_pre_feature_schema_is_upgraded_without_rewriting_existing_values(tmp_path):
    from backend.app.db import SCHEMA

    database = tmp_path / "matlens.db"
    # SCHEMA creates the legacy 13-column cases table; initialize performs additions.
    with connect(database) as db:
        db.executescript(SCHEMA)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(cases)")}
        assert "naming_json" not in columns and "app_managed" not in columns
        db.execute(
            "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy",
                "2026-10-05",
                "二門診",
                "1F",
                "M3-01",
                "底座",
                '["火警", "底座故障"]',
                "原位置",
                "原備註",
                str(tmp_path / "photos"),
                "底座/舊案件",
                0,
                "2026-10-05",
            ),
        )
        db.execute(
            "INSERT INTO custom_options VALUES (1,?,?,?)", ("issue", "底座故障", "2026-10-05")
        )
        before = tuple(db.execute("SELECT * FROM cases").fetchone())
    client = client_at(tmp_path)
    with connect(database) as db:
        assert tuple(db.execute("SELECT * FROM cases").fetchone())[:13] == before
    refs = client.get("/api/reference-values").json()
    assert "底座故障" in refs["fire_details"] and "底座故障" in refs["issues"]
    assert client_at(tmp_path).get("/api/cases/legacy").json()["notes"] == "原備註"
