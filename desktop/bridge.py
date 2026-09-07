from __future__ import annotations

import threading
from collections.abc import Callable


class DraftState:
    def __init__(self):
        self._lock = threading.Lock()
        self._sequence = -1
        self._dirty = False
        self._saving = False

    def update_state(self, sequence: int, dirty: bool, saving: bool) -> None:
        with self._lock:
            if sequence > self._sequence:
                self._sequence = sequence
                self._dirty = bool(dirty)
                self._saving = bool(saving)


class DesktopBridge(DraftState):
    def __init__(self, updates, close_window):
        super().__init__()
        self._updates = updates
        self._close_window = close_window

    def update_status(self):
        return self._updates.status()

    def check_update(self, channel="stable"):
        return self._updates.check(channel)

    def download_update(self):
        return self._updates.fetch_package()

    def install_update(self, dirty: bool, saving: bool):
        with self._lock:
            if dirty or saving or self._dirty or self._saving:
                return {"error": "請先儲存或清除目前案件，再安裝更新。"}
            result = self._updates.launch_installer()
        if result.get("ok"):
            # Let the bridge response reach React before closing the WebView.
            threading.Timer(0.5, self._close_window).start()
        return result


def confirm_close(state: DraftState, confirm: Callable[[str, str], bool]) -> bool:
    # WinForms closing runs on the UI thread. Never evaluate JavaScript here:
    # WebView2 needs that same thread to complete its async result -> deadlock.
    with state._lock:
        dirty, saving = state._dirty, state._saving
    if saving:
        confirm("正在儲存", "照片正在儲存，請完成後再關閉。")
        return False
    if dirty:
        return confirm("尚未儲存", "目前有尚未儲存的照片或案件資料，確定關閉？")
    return True
