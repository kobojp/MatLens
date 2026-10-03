from __future__ import annotations


class StorageError(Exception):
    pass


class DuplicatePhotoError(StorageError):
    def __init__(self, duplicates: list[dict[str, str]]) -> None:
        super().__init__("發現重複照片")
        self.duplicates = duplicates
