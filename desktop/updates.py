from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from desktop.data import resource_root, user_data_dir
from desktop.installation import running_installation
from desktop.update_core import download, verify_manifest, verify_package, version_key
from desktop.update_log import clean_text, record_event
from desktop.version import VERSION


def installed_directory() -> Path:
    target, _ = running_installation()
    if target is None:
        raise ValueError("請先使用安裝精靈安裝 MatLens。")
    return target


class UpdateService:
    def __init__(self, data_dir: Path, *, enabled: bool = True):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._manifest = None
        self._job_dir = None
        self._session_id = uuid.uuid4().hex
        self._stage = "idle"
        target, mode = running_installation()
        self._source = json.loads(
            (resource_root() / "desktop" / "update-source.json").read_text(encoding="utf-8")
        )
        self._state = {
            "current": VERSION, "phase": "idle", "channel": "stable", "progress": 0,
            "message": "可檢查是否有新版本。", "version": "", "notes": "",
            "executable": str(Path(sys.executable).resolve()),
            "database": str((data_dir / "matlens.db").resolve()),
            "installation_mode": mode,
            "log_directory": str((data_dir / "logs/updates").resolve()), "log_error": "",
            "installable": bool(getattr(sys, "frozen", False)
                                and target is not None
                                and data_dir.resolve() == user_data_dir().resolve()
                                and not os.getenv("MATLENS_DESKTOP_DATA_DIR")),
        }
        self._enabled = enabled
        self._result_mtime = None
        self._event("session.start", installation_mode=mode, os_version=platform.version())

    def _event(self, event: str, **details):
        job_id = self._job_dir.name if self._job_dir is not None else self._session_id
        warning = record_event(self.data_dir, job_id,
                               "client", event, version=self._state.get("version", ""), **details)
        if warning:
            self._set(log_error=warning)

    def _step(self, stage: str, **details):
        self._stage = stage
        self._event(stage, **details)

    def status(self) -> dict:
        # The worker finishes its report after the new app starts. Refresh on change.
        report = self.data_dir / "updates" / "last-result.json"
        try:
            modified = report.stat().st_mtime_ns if report.exists() else None
            if modified is not None and modified != self._result_mtime:
                result = json.loads(report.read_text(encoding="utf-8"))
                if not isinstance(result, dict):
                    raise ValueError("更新結果格式不正確")
                if result.get("ok") and result.get("version"):
                    wrong_version = version_key(result["version"]) > version_key(VERSION)
                    if wrong_version:
                        result = {**result, "ok": False,
                                  "message": f"更新尚未在此程式生效，仍在執行 {VERSION}。"
                                  "請從桌面捷徑開啟已更新的 MatLens，並核對程式位置。"}
                self._set(last_result=result)
                self._result_mtime = modified
                self._event("result.observed", result=result)
        except (ValueError, OSError):
            logging.exception("Cannot read updater result")
        pending = self.data_dir / "updates" / "pending.json"
        try:
            if pending.exists():
                expected = json.loads(pending.read_text("utf-8"))
                with self._lock:
                    result = self._state.get("last_result", {})
                if result.get("job_id") != expected["job_id"]:
                    self._set(last_result={"ok": False, "message":
                        f"更新至 {expected['version']} 尚待確認，目前執行 {VERSION}。"
                        "若重開後仍相同，請核對程式位置及更新紀錄。"})
        except (ValueError, OSError, KeyError):
            logging.exception("Cannot read pending update")
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
                self._event("failed", failed_stage=self._stage, error=error)
                message = (clean_text(str(error)) if isinstance(error, ValueError)
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
        self._job_dir = self.data_dir / "updates" / uuid.uuid4().hex
        self._set(job_id=self._job_dir.name)
        self._step("check.prepare", channel=channel)

        def work():
            if not self._source.get("public_key") or not self._source.get(channel):
                raise ValueError("尚未設定已簽章的更新來源，請聯絡程式維護者。")
            job_dir = self._job_dir
            job_dir.mkdir(parents=True)
            metadata = job_dir / "manifest.json"
            self._step("check.download_manifest", url=self._source[channel])
            download(self._source[channel], metadata, 128 * 1024)
            self._step("check.verify_manifest")
            manifest = verify_manifest(metadata.read_bytes(), self._source["public_key"], channel)
            self._manifest, self._job_dir = manifest, job_dir
            self._set(job_id=job_dir.name)
            newer = version_key(manifest["version"]) > version_key(VERSION)
            self._set(phase="available" if newer else "current", version=manifest["version"],
                      notes=manifest["notes"],
                      message="有新版本可下載。" if newer else "目前已是最新版本。")
            self._event("check.complete", newer=newer)
        self._run(work)
        return self.status()

    def fetch_package(self) -> dict:
        if not self._state["installable"]:
            return {"error": "請先使用 MatLens 安裝精靈安裝，再使用程式內更新。"}
        if not self._begin("downloading", {"available"}):
            return self.status()
        self._set(message="正在下載並驗證更新包…")

        def work():
            package = self._job_dir / "package.zip"
            self._step("download.package", expected_bytes=self._manifest["size"])
            download(self._manifest["url"], package, self._manifest["size"],
                     lambda count: self._set(progress=min(99, int(
                         count * 100 / self._manifest["size"]))))
            self._step("download.verify_package", received_bytes=package.stat().st_size)
            verify_package(package, self._manifest)
            self._event("download.complete", verified=True)
            self._set(phase="ready", progress=100, message="驗證完成，請儲存案件後安裝並重新啟動。")
        self._run(work)
        return self.status()

    def launch_installer(self) -> dict:
        if not self._state["installable"]:
            return {"error": "只有預設安裝位置的桌面版可自動更新。"}
        if not self._begin("installing", {"ready"}):
            return {"error": "更新包尚未準備完成。"}
        pending = None
        try:
            self._step("install.verify_package")
            # Re-verify at the boundary; worker verifies again after parent exits.
            verify_package(self._job_dir / "package.zip", self._manifest)
            self._step("install.prepare", target=str(installed_directory()))
            job = self._job_dir / "job.json"
            job.write_text(json.dumps({"parent_pid": os.getpid(),
                                       "target": str(installed_directory()),
                                       "channel": self._state["channel"]}), encoding="utf-8")
            helper = self._job_dir / "MatLensUpdater.exe"
            shutil.copy2(installed_directory() / "MatLensUpdater.exe", helper)
            pending = self.data_dir / "updates" / "pending.json"
            staged = pending.with_suffix(".tmp")
            staged.write_text(json.dumps({"job_id": self._job_dir.name,
                                          "version": self._manifest["version"],
                                          "target": str(installed_directory())}), "utf-8")
            staged.replace(pending)
            self._step("install.launch_worker", target=str(installed_directory()))
            worker = subprocess.Popen([str(helper), str(job)], cwd=self._job_dir,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            self._event("install.handoff", worker_pid=getattr(worker, "pid", None))
            self._set(message="即將關閉並更新，請稍候；新版會自動開啟。")
            return {"ok": True}
        except Exception as error:
            self._event("failed", failed_stage=self._stage, error=error)
            # Only this attempt's marker; retain prior worker reports.
            if pending is not None and pending.exists():
                pending.unlink()
            self._set(phase="error", message="無法啟動更新器，原程式未變更。")
            return {"error": "無法啟動更新器，請重新檢查更新。"}

    def open_logs(self) -> dict:
        try:
            folder = (self.data_dir / "logs/updates").resolve()
            folder.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["explorer.exe", str(folder)])
            return {"ok": True}
        except OSError as error:
            self._event("logs.open_failed", error=error)
            return {"error": "無法開啟更新紀錄資料夾，請確認檔案總管可用。"}

    def diagnostics(self) -> dict:
        updates = self.data_dir / "updates"
        jobs = []
        if updates.exists():
            folders = sorted((folder for folder in updates.iterdir()
                              if folder.is_dir() and len(folder.name) == 32
                              and all(char in "0123456789abcdef" for char in folder.name)
                              and folder.resolve() == folder.absolute()),
                             key=lambda folder: folder.stat().st_mtime_ns, reverse=True)
            for folder in folders[:5]:
                reports = {}
                for name in ["job.json", "progress.json", "probe.json",
                             "recovery.json", "startup.json"]:
                    path = folder / name
                    if path.is_file() and path.resolve().parent == folder.resolve():
                        try:
                            reports[name] = (json.loads(path.read_text("utf-8"))
                                             if path.stat().st_size <= 256 * 1024
                                             else {"error": "紀錄過大，請在本機查看"})
                        except (ValueError, OSError):
                            reports[name] = {"error": "紀錄無法讀取"}
                jobs.append({"job_id": folder.name, "reports": reports})
        return {"status": self.status(), "jobs": jobs,
                "notice": "這份診斷只包含本機更新資訊；對外分享前請遮蔽使用者路徑。"}
