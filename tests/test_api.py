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


def create_case(
    client: TestClient,
    colors: list[tuple[int, int, int]],
    *,
    storage_month: str = "8月",
    storage_subfolder: str = "底座",
) -> object:
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
            "storage_month": storage_month,
            "storage_subfolder": storage_subfolder,
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
    (tmp_path / "photos" / "8月" / "底座").mkdir(parents=True)
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
    assert Path(created["folder_path"]).parts[:2] == ("8月", "底座")

    listed = client.get("/api/cases", params={"q": "M3-07"}).json()
    assert listed["total"] == 1
    detail = client.get(f"/api/cases/{created['id']}").json()
    assert detail["building"] == "二門診"
    assert client.get(detail["photos"][0]["content_url"]).status_code == 200


def test_duplicate_photo_is_rejected_without_new_case(client: TestClient) -> None:
    assert client.post(
        "/api/settings/storage/folders",
        json={"month": "8月", "subfolders": ["底座"]},
    ).status_code == 201
    colors = [(180, 20, 20), (20, 180, 20), (20, 20, 180)]
    first = create_case(client, colors)
    assert first.status_code == 201

    second = create_case(client, colors)
    assert second.status_code == 409
    assert "重複照片" in second.json()["detail"]["message"]
    assert client.get("/api/cases").json()["total"] == 1


def test_invalid_image_is_rejected(client: TestClient) -> None:
    assert client.post(
        "/api/settings/storage/folders",
        json={"month": "8月", "subfolders": ["底座"]},
    ).status_code == 201
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
            "storage_month": "8月",
            "storage_subfolder": "底座",
        },
        files=[("photos", ("fake.jpg", b"not-an-image", "image/jpeg"))],
    )
    assert response.status_code == 400
    assert "不是可讀取的圖片" in response.json()["detail"]


def test_storage_directory_can_be_changed(client: TestClient, tmp_path: Path) -> None:
    assert client.post(
        "/api/settings/storage/folders",
        json={"month": "8月", "subfolders": ["底座"]},
    ).status_code == 201
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

    assert client.post(
        "/api/settings/storage/folders",
        json={"month": "8月", "subfolders": ["底座"]},
    ).status_code == 201

    response = create_case(client, [(181, 21, 21), (21, 181, 21), (21, 21, 181)])
    assert response.status_code == 201
    created = response.json()
    assert Path(created["storage_root"]) == custom_root.resolve()
    assert (custom_root / created["folder_path"]).is_dir()
    assert client.get(original_photo_url).status_code == 200


def test_storage_tree_scans_months_and_subfolders(client: TestClient, tmp_path: Path) -> None:
    photo_root = tmp_path / "photos"
    for relative in ["8月/底座", "8月/模組", "9月/底座", "9月/探頭"]:
        (photo_root / relative).mkdir(parents=True)
    (photo_root / "9月" / "not-a-folder.txt").write_text("x", encoding="utf-8")
    (photo_root / "2026" / "9月").mkdir(parents=True)

    response = client.get("/api/settings/storage/tree", params={"work_date": "2026-09-05"})

    assert response.status_code == 200
    assert response.json() == {
        "root": str(photo_root.resolve()),
        "target_month": "9月",
        "month_exists": True,
        "months": [
            {"name": "8月", "subfolders": ["底座", "模組"]},
            {"name": "9月", "subfolders": ["底座", "探頭"]},
        ],
    }


def test_missing_month_and_custom_subfolders_can_be_created(
    client: TestClient, tmp_path: Path
) -> None:
    missing = client.get(
        "/api/settings/storage/tree", params={"work_date": "2026-10-05"}
    ).json()
    assert missing["target_month"] == "10月"
    assert missing["month_exists"] is False

    created = client.post(
        "/api/settings/storage/folders",
        json={"month": "10月", "subfolders": ["底座", "自訂設備"]},
    )

    assert created.status_code == 201
    assert (tmp_path / "photos" / "10月" / "底座").is_dir()
    assert (tmp_path / "photos" / "10月" / "自訂設備").is_dir()
    assert created.json()["month"]["subfolders"] == ["底座", "自訂設備"]


def test_case_requires_existing_selected_destination(client: TestClient) -> None:
    response = create_case(
        client,
        [(180, 20, 20)],
        storage_month="9月",
        storage_subfolder="探頭",
    )
    assert response.status_code == 400
    assert "不存在" in response.json()["detail"]


@pytest.mark.parametrize(
    ("month", "subfolder"),
    [("../9月", "底座"), ("9月", "../底座"), ("C:\\temp", "底座"), ("13月", "底座")],
)
def test_storage_folder_creation_rejects_unsafe_names(
    client: TestClient, month: str, subfolder: str
) -> None:
    response = client.post(
        "/api/settings/storage/folders",
        json={"month": month, "subfolders": [subfolder]},
    )
    assert response.status_code == 400
    assert "目錄名稱" in response.json()["detail"]


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
