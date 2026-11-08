from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from desktop.bridge import DesktopBridge


def read(monkeypatch, value):
    from desktop.clipboard import read_images

    monkeypatch.setattr("desktop.clipboard.ImageGrab.grabclipboard", lambda: value)
    return read_images()


def test_clipboard_bitmap_is_png_without_changing_source(monkeypatch):
    picture = Image.new("RGB", (20, 30), "green")
    result = read(monkeypatch, picture)
    item = result["images"][0]
    assert item["mime"] == "image/png"
    with Image.open(io.BytesIO(base64.b64decode(item["data"]))) as decoded:
        assert decoded.size == (20, 30)
    assert picture.size == (20, 30)


def test_clipboard_file_images_keep_original_bytes(tmp_path, monkeypatch):
    path = tmp_path / "source.jpg"
    Image.new("RGB", (30, 20), "red").save(path)
    original = path.read_bytes()
    result = read(monkeypatch, [str(path)])
    assert base64.b64decode(result["images"][0]["data"]) == original
    assert path.read_bytes() == original


@pytest.mark.parametrize("value", [None, [], ["https://example.com/image.png"]])
def test_clipboard_empty_or_text_has_readable_error(monkeypatch, value):
    result = read(monkeypatch, value)
    assert "error" in result
    assert not result.get("images")


def test_clipboard_access_failure_and_bridge_are_readable(monkeypatch):
    from desktop import clipboard

    def fail():
        raise OSError("Clipboard busy")

    monkeypatch.setattr(clipboard.ImageGrab, "grabclipboard", fail)
    bridge = DesktopBridge(None, lambda: None)
    assert "無法讀取剪貼簿" in bridge.read_clipboard_images()["error"]
