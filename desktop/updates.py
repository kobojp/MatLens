from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from desktop.data import resource_root, user_data_dir
from desktop.update_core import download, verify_manifest, verify_package, version_key
from desktop.version import VERSION


def installed_directory() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / "MatLens"


class UpdateService:
    def __init__(self, data_dir: Path, *, enabled: bool = True):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._manifest = None
        self._job_dir = None
        self._source = json.loads(
            (resource_root() / "desktop" / "update-source.json").read_text(encoding="utf-8")
        )
        self._state = {
            "current": VERSION, "phase": "idle", "channel": "stable", "progress": 0,
            "message": "可檢查是否有新版本。", "version": "", "notes": "",
            "installable": bool(getattr(sys, "frozen", False)
                                and Path(sys.executable).parent.resolve()
                                == installed_directory().resolve()
                                and data_dir.resolve() == user_data_dir().resolve()
                                and not os.getenv("MATLENS_DESKTOP_DATA_DIR")),
        }
        self._enabled = enabled
        self._result_mtime = None

    def status(self) -> dict:
        # The worker finishes its report after the new app starts. Refresh on change.
        report = self.data_dir / "updates" / "last-result.json"
        try:
            modified = report.stat().st_mtime_ns if report.exists() else None
            if modified is not None and modified != self._result_mtime:
                result = json.loads(report.read_text(encoding="utf-8"))
                self._set(last_result=result)
                self._result_mtime = modified
        except (ValueError, OSError):
            logging.exception("Cannot read updater result")
        with self._lock:
            return dict(self._state)

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    def _begin(self, phase: str, allowed: set[str]) -> bool:
        with self._lock:
            if self._state["phase"] not in allowed:
                return False
            self._state.update(phase=phase, progress=0)
            return True

    def _run(self, action):
        def work():
            try:
                action()
            except Exception as error:
                logging.exception("Update operation failed")
                message = (str(error) if isinstance(error, ValueError)
                           else "無法取得更新，請確認網路或稍後重試；原版本仍可使用。")
                self._set(phase="error", message=message)
        threading.Thread(target=work, daemon=True).start()

    def check(self, channel: str = "stable") -> dict:
        if channel not in {"stable", "preview"}:
            return {"error": "請選擇正式版或測試版。"}
        if not self._enabled:
            return self.status()
        if not self._begin("checking", {"idle", "available", "current", "error", "ready"}):
            return self.status()
        self._set(channel=channel, message="正在檢查更新…", version="", notes="")

        def work():
            if not self._source.get("public_key") or not self._source.get(channel):
                raise ValueError("尚未設定已簽章的更新來源，請聯絡程式維護者。")
            job_dir = self.data_dir / "updates" / uuid.uuid4().hex
            job_dir.mkdir(parents=True)
            metadata = job_dir / "manifest.json"
            download(self._source[channel], metadata, 128 * 1024)
            manifest = verify_manifest(metadata.read_bytes(), self._source["public_key"], channel)
            self._manifest, self._job_dir = manifest, job_dir
            newer = version_key(manifest["version"]) > version_key(VERSION)
            self._set(phase="available" if newer else "current", version=manifest["version"],
                      notes=manifest["notes"],
                      message="有新版本可下載。" if newer else "目前已是最新版本。")
        self._run(work)
        return self.status()

    def fetch_package(self) -> dict:
        if not self._state["installable"]:
            return {"error": "請先執行 Install-MatLens.cmd 安裝，再使用程式內更新。"}
        if not self._begin("downloading", {"available"}):
            return self.status()
        self._set(message="正在下載並驗證更新包…")

        def work():
            package = self._job_dir / "package.zip"
            download(self._manifest["url"], package, self._manifest["size"],
                     lambda count: self._set(progress=min(99, int(
                         count * 100 / self._manifest["size"]))))
            verify_package(package, self._manifest)
            self._set(phase="ready", progress=100, message="驗證完成，請儲存案件後安裝並重新啟動。")
        self._run(work)
        return self.status()

    def launch_installer(self) -> dict:
        if not self._state["installable"]:
            return {"error": "只有預設安裝位置的桌面版可自動更新。"}
        if not self._begin("installing", {"ready"}):
            return {"error": "更新包尚未準備完成。"}
        try:
            # Re-verify at the boundary; worker verifies again after parent exits.
            verify_package(self._job_dir / "package.zip", self._manifest)
            job = self._job_dir / "job.json"
            job.write_text(json.dumps({"parent_pid": os.getpid(),
                                       "channel": self._state["channel"]}), encoding="utf-8")
            helper = self._job_dir / "MatLensUpdater.exe"
            shutil.copy2(installed_directory() / "MatLensUpdater.exe", helper)
            subprocess.Popen([str(helper), str(job)], cwd=self._job_dir,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            self._set(message="即將關閉並更新，請稍候；新版會自動開啟。")
            return {"ok": True}
        except Exception:
            logging.exception("Cannot start updater")
            self._set(phase="error", message="無法啟動更新器，原程式未變更。")
            return {"error": "無法啟動更新器，請重新檢查更新。"}
