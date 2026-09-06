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
