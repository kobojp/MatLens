from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class CaseCreate(BaseModel):
    work_date: date
    building: str = Field(min_length=1, max_length=40)
    floor: str = Field(min_length=1, max_length=20)
    address_code: str = Field(min_length=1, max_length=60)
    material: str = Field(min_length=1, max_length=40)
    issues: list[str] = Field(min_length=1, max_length=8)
    location: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=500)

    @field_validator("building", "floor", "address_code", "material", "location", "notes")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("issues")
    @classmethod
    def clean_issues(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not cleaned:
            raise ValueError("至少選擇一個問題")
        return cleaned


class FireNamingSetting(BaseModel):
    include_material: StrictBool = True


class CaseEditPhoto(BaseModel):
    photo_id: str | None = Field(default=None, min_length=1, max_length=80)
    upload_index: int | None = Field(default=None, ge=0, le=29, strict=True)
    role: str

    @model_validator(mode="after")
    def validate_selection(self):
        from .config import PHOTO_ROLES

        if (self.photo_id is None) == (self.upload_index is None) or self.role not in PHOTO_ROLES:
            raise ValueError("照片來源或角色不正確")
        return self


class CaseEdit(CaseCreate):
    token: str = Field(min_length=64, max_length=64)
    apply_naming: StrictBool = False
    include_material: StrictBool = True
    include_date: StrictBool = True
    confirm_managed: StrictBool = False
    name_with_sequence: StrictBool = False
    photos: list[CaseEditPhoto] | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("building", "floor", "address_code", "material")
    @classmethod
    def required_edit_field(cls, value: str) -> str:
        if not value:
            raise ValueError("案件必填欄位不可空白")
        return value

    @field_validator("issues")
    @classmethod
    def single_issue(cls, values: list[str]) -> list[str]:
        if len(values) != 1 and not (len(values) == 2 and values[0] == "火警"):
            raise ValueError("問題只能選擇一項，火警可再選一個細項")
        return values


class StorageSettingsUpdate(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class UIPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: Literal["classic", "tiles"] = "tiles"
    panel_position: Literal["right", "top"] = "right"
    tile_size: Literal["medium", "large"] = "large"
    panel_collapsed: StrictBool = False


class StorageSelection(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    subfolder: str = Field(default="", max_length=80)
    with_date: StrictBool = True

    @field_validator("path", "subfolder")
    @classmethod
    def strip_selection(cls, value: str) -> str:
        return value.strip()


class StorageFoldersCreate(BaseModel):
    month: str = Field(min_length=1, max_length=80)
    subfolders: list[str] = Field(min_length=1, max_length=20)

    @field_validator("month")
    @classmethod
    def normalize_month(cls, value: str) -> str:
        return value.strip()

    @field_validator("subfolders")
    @classmethod
    def normalize_subfolders(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not cleaned:
            raise ValueError("至少需要一個子目錄")
        return cleaned


class CustomOptionCreate(BaseModel):
    value: str = Field(min_length=1, max_length=40)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("選項不可空白")
        return normalized


class OverviewAutoScan(BaseModel):
    enabled: bool


class OverviewExport(BaseModel):
    source: Literal["db", "disk"] = "db"
    material: str = ""
    building: str = ""
    path: str = ""
    mode: Literal["light", "standalone"] = "light"
    reveal: bool = True


class NameSequenceSetting(BaseModel):
    enabled: bool


class RoleOrderSetting(BaseModel):
    roles: list[str] = Field(min_length=1, max_length=8)

    @field_validator("roles")
    @classmethod
    def unique_known_roles(cls, values: list[str]) -> list[str]:
        from .config import PHOTO_ROLES

        cleaned = list(dict.fromkeys(value.strip() for value in values))
        unknown = [value for value in cleaned if value not in PHOTO_ROLES]
        if unknown:
            raise ValueError(f"未知照片分類：{', '.join(unknown)}")
        return cleaned
