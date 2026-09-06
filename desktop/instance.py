from __future__ import annotations

import ctypes
import hashlib
from ctypes import wintypes
from pathlib import Path


class SingleInstance:
    """Named Windows mutex and event: a second launch activates the first window."""

    def __init__(self, data_dir: Path):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.CreateEventW.argtypes = [
            ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR,
        ]
        self.api.CreateEventW.restype = wintypes.HANDLE
        self.api.SetEvent.argtypes = [wintypes.HANDLE]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        key = hashlib.sha256(str(data_dir.resolve()).casefold().encode()).hexdigest()[:24]
        self.mutex = self.api.CreateMutexW(None, False, f"Local\\MatLens-{key}")
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.already_running = ctypes.get_last_error() == 183
        self.event = self.api.CreateEventW(None, False, False, f"Local\\MatLens-activate-{key}")
        if not self.event:
            self.api.CloseHandle(self.mutex)
            raise ctypes.WinError(ctypes.get_last_error())
        if self.already_running:
            self.api.SetEvent(self.event)

    def wait_activation(self) -> bool:
        return self.api.WaitForSingleObject(self.event, 250) == 0

    def close(self) -> None:
        self.api.CloseHandle(self.event)
        self.api.CloseHandle(self.mutex)
