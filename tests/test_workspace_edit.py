import json
import shutil
import uuid
from pathlib import Path

import pytest

from backend.app.db import connect
from tests.test_api import jpeg_bytes
from tests.test_fire_edit import client_at, fire_case, update_body


def save_workspace(client, case, *, files=(), **changes):
    edit = client.get("/api/cases/" + case["id"] + "/edit").json()
    body = update_body(edit, **changes)
    return client.post(
        "/api/cases/" + case["id"] + "/save", data={"change": json.dumps(body)}, files=list(files)
    )


def test_workspace_save_adds_reorders_roles_and_archives_originals(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    old = tmp_path / "photos" / case["folder_path"]
    original = (old / case["photos"][0]["stored_name"]).read_bytes()
    response = save_workspace(
        client,
        case,
        address_code="M3-02",
        photos=[
            {"upload_index": 0, "role": "中"},
            {"photo_id": case["photos"][0]["id"], "role": "完成"},
        ],
        files=[("photos", ("new.jpg", jpeg_bytes((1, 200, 40)), "image/jpeg"))],
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["id"] == case["id"] and saved["photo_count"] == 2
    assert [p["role"] for p in saved["photos"]] == ["中", "完成"]
    assert saved["photos"][1]["id"] == case["photos"][0]["id"]
    assert client.get(saved["photos"][1]["content_url"]).content == original
    assert (Path(saved["photo_backup"]) / case["photos"][0]["stored_name"]).read_bytes() == original
    assert not old.exists() and client.get("/api/cases").json()["total"] == 1
    removed = save_workspace(
        client, saved, photos=[{"photo_id": saved["photos"][0]["id"], "role": "中"}]
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["photo_count"] == 1
    assert (
        Path(removed.json()["photo_backup"]) / saved["photos"][1]["stored_name"]
    ).read_bytes() == original
    scan = client.post(
        "/api/cases/rescan", params={"path": str(tmp_path / "photos"), "prune": False}
    )
    assert scan.status_code == 200 and client.get("/api/cases").json()["total"] == 1


def test_unchanged_photos_are_not_renamed_or_copied(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    response = save_workspace(
        client, case, notes="只改備註", photos=[{"photo_id": case["photos"][0]["id"], "role": "前"}]
    )
    assert response.status_code == 200, response.text
    assert response.json()["photos"] == case["photos"]
    assert not list((tmp_path / "photos/.matlens-history").glob("*"))


@pytest.mark.parametrize(
    "selection",
    [
        [],
        [{"photo_id": "someone-else", "role": "前"}],
        [{"upload_index": 7, "role": "前"}],
        [{"upload_index": 0, "role": "未知角色"}],
    ],
)
def test_invalid_photo_changes_preserve_original(tmp_path, selection):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    response = save_workspace(client, case, photos=selection)
    assert response.status_code in [400, 422], response.text
    assert client.get("/api/cases/" + case["id"]).json()["photos"] == case["photos"]


def test_workspace_failure_restores_sqlite_and_files(tmp_path, monkeypatch):
    from backend.app.storage import workspace_edit

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)

    def fail(*args):
        raise OSError("injected write failure")

    monkeypatch.setattr(workspace_edit, "_write_case", fail)
    response = save_workspace(
        client, case, photos=[{"photo_id": case["photos"][0]["id"], "role": "中"}]
    )
    assert response.status_code == 400
    assert client.get("/api/cases/" + case["id"]).json()["photos"] == case["photos"]
    assert (tmp_path / "photos" / case["folder_path"] / case["photos"][0]["stored_name"]).is_file()


def test_photo_recovery_keeps_database_write_lock(tmp_path, monkeypatch):
    import sqlite3

    from backend.app.storage import workspace_edit

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    restore = workspace_edit.recover_photo_edit

    def fail(*args):
        raise OSError("injected failure")

    def locked_restore(connection, path, job):
        with connect(tmp_path / "matlens.db") as other:
            other.execute("PRAGMA busy_timeout=0")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
        return restore(connection, path, job)

    monkeypatch.setattr(workspace_edit, "_write_case", fail)
    monkeypatch.setattr(workspace_edit, "recover_photo_edit", locked_restore)
    response = save_workspace(
        client, case, photos=[{"photo_id": case["photos"][0]["id"], "role": "中"}]
    )
    assert response.status_code == 400


def test_bad_image_does_not_replace_old_case(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    response = save_workspace(
        client,
        case,
        photos=[{"upload_index": 0, "role": "前"}],
        files=[("photos", ("bad.jpg", b"not an image", "image/jpeg"))],
    )
    assert response.status_code == 400
    assert client.get("/api/cases/" + case["id"]).json()["photos"] == case["photos"]


def test_existing_photo_also_registered_elsewhere_can_still_change_role(tmp_path):
    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    old = tmp_path / "photos" / case["folder_path"]
    shutil.copytree(old, old.with_name("another-registered-copy"))
    client.post("/api/cases/rescan", params={"path": str(tmp_path / "photos"), "prune": False})
    assert client.get("/api/cases").json()["total"] == 2
    response = save_workspace(
        client, case, photos=[{"photo_id": case["photos"][0]["id"], "role": "中"}]
    )
    assert response.status_code == 200, response.text
    assert response.json()["photos"][0]["role"] == "中"


@pytest.mark.parametrize("phase", ["archived", "installed", "committed"])
@pytest.mark.parametrize("renamed", [False, True])
def test_photo_exchange_recovers_across_process_interruptions(tmp_path, phase, renamed):
    from backend.app.storage.workspace_edit import _photo_journal

    client = client_at(tmp_path)
    case = fire_case(client, tmp_path)
    root = tmp_path / "photos"
    old = root / case["folder_path"]
    new = old.with_name("new-name") if renamed else old
    stage = root / ".staging" / uuid.uuid4().hex
    archive = root / ".matlens-history" / uuid.uuid4().hex
    stage.parent.mkdir(exist_ok=True)
    archive.parent.mkdir(exist_ok=True)
    shutil.copytree(old, stage)
    revision = uuid.uuid4().hex
    journal = _photo_journal(
        tmp_path / "matlens.db", case["id"], root, old, new, archive, stage, revision
    )
    old.rename(archive)
    if phase != "archived":
        stage.rename(new)
    if phase == "committed":
        with connect(tmp_path / "matlens.db") as db:
            db.execute(
                "UPDATE cases SET folder_path=?,edit_revision=? WHERE id=?",
                (new.relative_to(root).as_posix(), revision, case["id"]),
            )
    client_at(tmp_path)
    assert not journal.exists()
    assert (new if phase == "committed" else old).is_dir()
    assert archive.exists() == (phase == "committed")
