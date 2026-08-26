from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


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


class StorageSettingsUpdate(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class CustomOptionCreate(BaseModel):
    value: str = Field(min_length=1, max_length=40)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("選項不可空白")
        return normalized
