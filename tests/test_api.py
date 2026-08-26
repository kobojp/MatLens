from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import create_app


def jpeg_bytes(color: tuple[int, int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (80, 60), color).save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        database_path=tmp_path / "matlens.db",
        photo_root=tmp_path / "photos",
        frontend_dist=tmp_path / "missing-frontend",
    )
    return TestClient(app)


def create_case(client: TestClient, colors: list[tuple[int, int, int]]) -> object:
    roles = ["前", "中", "完成"][: len(colors)]
    return client.post(
        "/api/cases",
        data={
            "work_date": "2026-08-17",
            "building": "二門診",
            "floor": "3F",
            "address_code": "M3-07",
            "material": "底座",
            "issues": '["錯誤設備"]',
            "location": "走廊東側",
            "notes": "測試案件",
            "photo_roles": str(roles).replace("'", '"'),
        },
        files=[
            ("photos", (f"photo-{index}.jpg", jpeg_bytes(color), "image/jpeg"))
            for index, color in enumerate(colors, start=1)
        ],
    )


def test_health_and_reference_values(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    references = client.get("/api/reference-values").json()
    assert "底座" in references["materials"]
    assert references["photo_roles"][:3] == ["前", "中", "完成"]


def test_create_list_and_read_case(client: TestClient, tmp_path: Path) -> None:
    response = create_case(client, [(180, 20, 20), (20, 180, 20), (20, 20, 180)])
    assert response.status_code == 201
    created = response.json()
    assert created["is_complete"] is True
    assert [photo["stored_name"] for photo in created["photos"]] == [
        "01_前.jpg",
        "02_中.jpg",
        "03_完成.jpg",
    ]
    saved_folder = tmp_path / "photos" / created["folder_path"]
    assert saved_folder.is_dir()
    assert len(list(saved_folder.glob("*.jpg"))) == 3

    listed = client.get("/api/cases", params={"q": "M3-07"}).json()
    assert listed["total"] == 1
    detail = client.get(f"/api/cases/{created['id']}").json()
    assert detail["building"] == "二門診"
    assert client.get(detail["photos"][0]["content_url"]).status_code == 200


def test_duplicate_photo_is_rejected_without_new_case(client: TestClient) -> None:
    colors = [(180, 20, 20), (20, 180, 20), (20, 20, 180)]
    first = create_case(client, colors)
    assert first.status_code == 201

    second = create_case(client, colors)
    assert second.status_code == 409
    assert "重複照片" in second.json()["detail"]["message"]
    assert client.get("/api/cases").json()["total"] == 1


def test_invalid_image_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/cases",
        data={
            "work_date": "2026-08-17",
            "building": "二門診",
            "floor": "3F",
            "address_code": "M3-07",
            "material": "底座",
            "issues": '["錯誤設備"]',
            "photo_roles": '["前"]',
        },
        files=[("photos", ("fake.jpg", b"not-an-image", "image/jpeg"))],
    )
    assert response.status_code == 400
    assert "不是可讀取的圖片" in response.json()["detail"]


def test_storage_directory_can_be_changed(client: TestClient, tmp_path: Path) -> None:
    original = create_case(client, [(180, 20, 20), (20, 180, 20), (20, 20, 180)])
    assert original.status_code == 201
    original_photo_url = original.json()["photos"][0]["content_url"]

    custom_root = tmp_path / "自訂照片目錄"
    configured = client.post(
        "/api/settings/storage",
        json={"path": str(custom_root)},
    )
    assert configured.status_code == 200
    assert Path(configured.json()["path"]) == custom_root.resolve()

    response = create_case(client, [(181, 21, 21), (21, 181, 21), (21, 21, 181)])
    assert response.status_code == 201
    created = response.json()
    assert Path(created["storage_root"]) == custom_root.resolve()
    assert (custom_root / created["folder_path"]).is_dir()
    assert client.get(original_photo_url).status_code == 200


def test_custom_material_and_issue_are_persisted(client: TestClient) -> None:
    material = client.post(
        "/api/reference-values/material",
        json={"value": "消防泵"},
    )
    issue = client.post(
        "/api/reference-values/issue",
        json={"value": "壓力不足"},
    )
    assert material.status_code == 201
    assert issue.status_code == 201

    references = client.get("/api/reference-values").json()
    assert "消防泵" in references["materials"]
    assert "壓力不足" in references["issues"]

    duplicate = client.post(
        "/api/reference-values/material",
        json={"value": " 消防泵 "},
    )
    assert duplicate.status_code == 409


def test_custom_option_can_be_deleted_but_default_cannot(client: TestClient) -> None:
    assert client.post(
        "/api/reference-values/material",
        json={"value": "消防泵"},
    ).status_code == 201
    assert client.post(
        "/api/reference-values/issue",
        json={"value": "壓力不足"},
    ).status_code == 201

    references = client.get("/api/reference-values").json()
    assert references["custom_materials"] == ["消防泵"]
    assert references["custom_issues"] == ["壓力不足"]

    deleted = client.request(
        "DELETE",
        "/api/reference-values/material",
        json={"value": "消防泵"},
    )
    assert deleted.status_code == 200
    assert client.request(
        "DELETE",
        "/api/reference-values/issue",
        json={"value": "壓力不足"},
    ).status_code == 200
    references = client.get("/api/reference-values").json()
    assert "消防泵" not in references["materials"]
    assert "壓力不足" not in references["issues"]
    assert references["custom_materials"] == []
    assert references["custom_issues"] == []

    protected_default = client.request(
        "DELETE",
        "/api/reference-values/material",
        json={"value": "底座"},
    )
    assert protected_default.status_code == 404
