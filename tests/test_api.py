from __future__ import annotations

import io
import shutil
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
    assert references["photo_roles"][:4] == ["前", "中", "後", "完成"]


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


def test_after_and_complete_are_equivalent_completion_roles(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "photos" / "8月" / "底座").mkdir(parents=True)
    response = client.post(
        "/api/cases",
        data={
            "work_date": "2026-08-17",
            "building": "二門診",
            "floor": "3F",
            "address_code": "M3-08",
            "material": "底座",
            "issues": '["錯誤設備"]',
            "photo_roles": '["前", "中", "後"]',
            "storage_month": "8月",
            "storage_subfolder": "底座",
        },
        files=[
            ("photos", (f"photo-{index}.jpg", jpeg_bytes(color), "image/jpeg"))
            for index, color in enumerate(
                [(181, 20, 20), (20, 181, 20), (20, 20, 181)], start=1
            )
        ],
    )

    assert response.status_code == 201
    assert response.json()["is_complete"] is True
    assert response.json()["missing_roles"] == []
    assert response.json()["photos"][2]["stored_name"] == "03_後.jpg"


def test_cases_are_paginated(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "photos" / "8月" / "底座").mkdir(parents=True)
    for offset in range(3):
        response = create_case(
            client,
            [
                (180, 20 + offset * 20, 20),
                (20 + offset * 20, 180, 20),
                (20, 20 + offset * 20, 180),
            ],
        )
        assert response.status_code == 201

    first_page = client.get("/api/cases", params={"page": 1, "page_size": 2}).json()
    second_page = client.get("/api/cases", params={"page": 2, "page_size": 2}).json()

    assert first_page["total"] == 3
    assert first_page["pages"] == 2
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 1


def test_rescan_relinks_case_after_storage_path_changes(
    client: TestClient, tmp_path: Path
) -> None:
    old_root = tmp_path / "photos"
    (old_root / "8月" / "底座").mkdir(parents=True)
    created = create_case(client, [(185, 20, 20), (20, 185, 20), (20, 20, 185)]).json()
    photo_url = created["photos"][0]["content_url"]
    old_folder = old_root / created["folder_path"]
    new_root = tmp_path / "搬移後照片"
    new_folder = new_root / "今年" / old_folder.name
    new_folder.parent.mkdir(parents=True)
    shutil.move(old_folder, new_folder)

    assert client.get(photo_url).status_code == 404
    rescanned = client.post("/api/cases/rescan", params={"path": str(new_root)})

    assert rescanned.status_code == 200
    assert rescanned.json()["relinked"] == 1
    detail = client.get(f"/api/cases/{created['id']}").json()
    assert Path(detail["storage_root"]) == new_root.resolve()
    assert detail["folder_path"] == f"今年/{old_folder.name}"
    assert client.get(photo_url).status_code == 200


def test_rescan_uses_selected_current_root_even_when_old_folder_still_exists(
    client: TestClient, tmp_path: Path
) -> None:
    old_root = tmp_path / "photos"
    (old_root / "8月" / "底座").mkdir(parents=True)
    created = create_case(client, [(186, 20, 20), (20, 186, 20), (20, 20, 186)]).json()
    old_folder = old_root / created["folder_path"]
    new_root = tmp_path / "目前照片"
    new_folder = new_root / "最新分類" / old_folder.name
    new_folder.parent.mkdir(parents=True)
    shutil.copytree(old_folder, new_folder)

    rescanned = client.post("/api/cases/rescan", params={"path": str(new_root)})

    assert rescanned.status_code == 200
    assert rescanned.json()["relinked"] == 1
    detail = client.get(f"/api/cases/{created['id']}").json()
    assert Path(detail["storage_root"]) == new_root.resolve()
    assert detail["folder_path"] == f"最新分類/{old_folder.name}"


def test_rescan_imports_existing_free_path_case_into_case_list(
    client: TestClient, tmp_path: Path
) -> None:
    free_root = tmp_path / "既有自由路徑"
    case_folder = free_root / "底座" / "2026-09-22 二門診 3F M3-09 錯誤設備"
    case_folder.mkdir(parents=True)
    for index, (role, color) in enumerate(
        zip(
            ["前", "中", "後"],
            [(190, 20, 20), (20, 190, 20), (20, 20, 190)],
            strict=True,
        ),
        start=1,
    ):
        (case_folder / f"{index:02d}_{role}.jpg").write_bytes(jpeg_bytes(color))

    rescanned = client.post("/api/cases/rescan", params={"path": str(free_root)})
    listed = client.get("/api/cases").json()

    assert rescanned.status_code == 200
    assert rescanned.json()["imported"] == 1
    assert listed["total"] == 1
    assert listed["items"][0]["address_code"] == "M3-09"
    assert listed["items"][0]["is_complete"] is True

    repeated = client.post("/api/cases/rescan", params={"path": str(free_root)})
    assert repeated.json()["imported"] == 0
    assert client.get("/api/cases").json()["total"] == 1


def test_rescan_imports_free_path_case_without_date_prefix(
    client: TestClient, tmp_path: Path
) -> None:
    free_root = tmp_path / "無日期自由路徑"
    case_folder = free_root / "探頭" / "二門診 B2 D2-01 無回應"
    case_folder.mkdir(parents=True)
    for index, (role, color) in enumerate(
        zip(
            ["前", "中", "完成"],
            [(191, 20, 20), (20, 191, 20), (20, 20, 191)],
            strict=True,
        ),
        start=1,
    ):
        (case_folder / f"{index:02d}_{role}.jpg").write_bytes(jpeg_bytes(color))

    rescanned = client.post("/api/cases/rescan", params={"path": str(free_root)})
    listed = client.get("/api/cases").json()

    assert rescanned.json()["imported"] == 1
    assert listed["items"][0]["building"] == "二門診"
    assert listed["items"][0]["material"] == "探頭"
    assert listed["items"][0]["address_code"] == "D2-01"


def test_rescan_imports_legacy_and_current_folder_names(
    client: TestClient, tmp_path: Path
) -> None:
    free_root = tmp_path / "混合格式"
    for index in range(69):
        if index < 63:
            folder_name = f"2026-09-22_二門診_3F_M3-{index:02d}_錯誤設備"
        else:
            folder_name = f"2026-09-22 二門診 3F M3-{index:02d} 錯誤設備"
        case_folder = free_root / "底座" / folder_name
        case_folder.mkdir(parents=True)
        (case_folder / "01_前.jpg").write_bytes(jpeg_bytes((100 + index, 20, 20)))

    rescanned = client.post("/api/cases/rescan", params={"path": str(free_root)})

    assert rescanned.json()["imported"] == 69
    assert client.get("/api/cases").json()["total"] == 69


def test_rescan_imports_all_image_folders_with_camera_file_names(
    client: TestClient, tmp_path: Path
) -> None:
    material_root = tmp_path / "自由路徑" / "底座"
    for index in range(69):
        case_folder = material_root / f"案件-{index + 1:02d}"
        case_folder.mkdir(parents=True)
        (case_folder / f"IMG_{index + 1:04d}.JPG").write_bytes(
            jpeg_bytes((100 + index, 30, 30))
        )

    rescanned = client.post("/api/cases/rescan", params={"path": str(material_root)})
    listed = client.get("/api/cases").json()

    assert rescanned.json()["imported"] == 69
    assert listed["total"] == 69
    assert listed["items"][0]["material"] == "底座"


def test_rescan_removes_database_case_when_folder_is_missing(
    client: TestClient, tmp_path: Path
) -> None:
    photo_root = tmp_path / "photos"
    (photo_root / "8月" / "底座").mkdir(parents=True)
    created = create_case(client, [(195, 20, 20), (20, 195, 20), (20, 20, 195)]).json()
    shutil.rmtree(photo_root / created["folder_path"])
    current_root = tmp_path / "目前自由路徑"
    current_root.mkdir()

    rescanned = client.post("/api/cases/rescan", params={"path": str(current_root)})

    assert rescanned.json()["removed"] == 1
    assert client.get("/api/cases").json()["total"] == 0


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


# ── 自由路徑掃描功能 ──────────────────────────────────────────

def test_storage_scan_returns_subfolders(client: TestClient, tmp_path: Path) -> None:
    scan_root = tmp_path / "scanned"
    scan_root.mkdir()
    (scan_root / "二門診 5F M3-214 無回應").mkdir()
    (scan_root / "三門診 3F D2-001 錯誤設備").mkdir()

    response = client.get("/api/settings/storage/scan", params={"path": str(scan_root)})
    assert response.status_code == 200
    data = response.json()
    assert data["root"] == str(scan_root.resolve())
    assert "二門診 5F M3-214 無回應" in data["subfolders"]
    assert "三門診 3F D2-001 錯誤設備" in data["subfolders"]


def test_storage_scan_nonexistent_path(client: TestClient, tmp_path: Path) -> None:
    response = client.get(
        "/api/settings/storage/scan",
        params={"path": str(tmp_path / "does-not-exist")},
    )
    assert response.status_code == 400
    assert "不存在" in response.json()["detail"]


def test_create_case_free_mode(client: TestClient, tmp_path: Path) -> None:
    free_root = tmp_path / "自由路徑測試"
    subfolder = "二門診 5F M3-214 無回應"
    (free_root / subfolder).mkdir(parents=True)

    response = client.post(
        "/api/cases",
        data={
            "work_date": "2026-09-21",
            "building": "二門診",
            "floor": "5F",
            "address_code": "M3-214",
            "material": "探頭",
            "issues": '["無回應"]',
            "location": "",
            "notes": "",
            "photo_roles": '["前", "中", "完成"]',
            "storage_month": "",
            "storage_subfolder": subfolder,
            "free_scan_root": str(free_root),
        },
        files=[
            ("photos", (f"photo-{i}.jpg", jpeg_bytes(color), "image/jpeg"))
            for i, color in enumerate([(200, 10, 10), (10, 200, 10), (10, 10, 200)], start=1)
        ],
    )
    assert response.status_code == 201
    created = response.json()
    assert created["is_complete"] is True
    saved_folder = (free_root / subfolder / Path(created["folder_path"]).name)
    assert saved_folder.is_dir()
    assert len(list(saved_folder.glob("*.jpg"))) == 3
