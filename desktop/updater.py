"""Standalone worker. No photos are modified; old program directories are retained."""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

from desktop.data import resource_root, user_data_dir
from desktop.update_core import extract_package, verify_manifest, verify_package, version_key
from desktop.version import VERSION


def wait_for_parent(pid: int):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # Process already exited.
            return
        raise RuntimeError("無法確認主程式已關閉，停止更新。")
    try:
        if kernel.WaitForSingleObject(handle, 60000) != 0:
            raise RuntimeError("主程式尚未關閉。請儲存案件後重新更新。")
    finally:
        kernel.CloseHandle(handle)


def backup_database(database: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("更新前資料庫備份驗證失敗。")


def swap_program(target: Path, prepared: Path, previous: Path, start_and_check):
    """Caller supplies validated sibling directories. Retain both versions on failure."""
    target.rename(previous)
    try:
        prepared.rename(target)
        start_and_check(target)
    except Exception:
        if target.exists():
            target.rename(prepared)
        previous.rename(target)
        raise


def start_and_check(target: Path, report: Path, version: str):
    process = subprocess.Popen([str(target / "MatLens.exe"), "--startup-report", str(report)],
                               cwd=target)
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            if report.exists():
                result = json.loads(report.read_text(encoding="utf-8"))
                if result.get("ok") and result.get("version") == version:
                    return
                break
            if process.poll() is not None:
                break
            time.sleep(0.2)
        raise RuntimeError("新版未通過啟動檢查，已回復原程式。")
    except Exception:
        # This process was launched by us and remains hidden until health succeeds.
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=15)
        raise


def apply_update(job: Path):
    data = user_data_dir().resolve()
    work = job.resolve().parent
    updates = data / "updates"
    if (work.parent != updates or not len(work.name) == 32
            or any(c not in "0123456789abcdef" for c in work.name)
            or job.name != "job.json"):
        raise ValueError("更新工作目錄不正確。")
    target = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "MatLens"
    # Reject junctions/symlinks: never rename a redirected installation or user data.
    if target.resolve() != target.absolute() or not (target / "MatLens.exe").is_file():
        raise ValueError("安裝位置不正確，停止更新。")
    allowed = {"matlens.exe", "matlensupdater.exe", "_internal"}
    if any(child.name.lower() not in allowed for child in target.iterdir()):
        raise ValueError("安裝目錄含非程式檔案，為保護資料已停止自動更新。")
    params = json.loads(job.read_text(encoding="utf-8"))
    pid = params["parent_pid"]
    if type(pid) is not int or pid <= 0 or pid == os.getpid():
        raise ValueError("主程式識別碼不正確。")
    source = json.loads((resource_root() / "desktop" / "update-source.json").read_text("utf-8"))
    manifest = verify_manifest((work / "manifest.json").read_bytes(),
                               source["public_key"], params["channel"])
    if version_key(manifest["version"]) <= version_key(VERSION):
        raise ValueError("拒絕安裝相同或較舊版本。")
    verify_package(work / "package.zip", manifest)
    wait_for_parent(pid)
    from desktop.instance import SingleInstance

    guard = SingleInstance(data)
    if guard.already_running:
        guard.close()
        raise RuntimeError("MatLens 仍在執行，停止更新。")
    try:
        backup = data / "backups" / f"before-update-{work.name}.db"
        backup_database(data / "matlens.db", backup)
        unpacked = extract_package(work / "package.zip", work / "unpacked")
        # Real WebView2 + save/reload flow against an isolated temporary database.
        probe = work / "probe.json"
        subprocess.run([str(unpacked / "MatLens.exe"), "--self-test", "--report", str(probe)],
                       cwd=unpacked, timeout=90, check=True)
        probe_result = json.loads(probe.read_text("utf-8"))
        if not probe_result.get("ok") or probe_result.get("version") != manifest["version"]:
            raise RuntimeError("新版預先測試失敗，未替換程式。")
        suffix = uuid.uuid4().hex
        prepared = target.with_name(f"MatLens.next-{suffix}")
        previous = target.with_name(f"MatLens.previous-{suffix}")
        if prepared.resolve().parent != target.resolve().parent:
            raise ValueError("暫存安裝位置不正確。")
        shutil.copytree(unpacked, prepared)
        journal = {"target": str(target), "previous": str(previous), "prepared": str(prepared),
                   "backup": str(backup), "version": manifest["version"]}
        (work / "recovery.json").write_text(json.dumps(journal), encoding="utf-8")
    finally:
        guard.close()
    # New app needs the instance mutex. Update lock below prevents overlapping workers.
    swap_program(target, prepared, previous,
                 lambda folder: start_and_check(folder, work / "startup.json", manifest["version"]))
    return {"ok": True, "message": f"已更新至 {manifest['version']}。", **journal}


def main() -> int:
    updates = user_data_dir() / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    lock = updates / "install.lock"
    try:
        with lock.open("x", encoding="utf-8") as output:
            output.write(str(os.getpid()))
    except FileExistsError:
        return 1
    try:
        try:
            result = apply_update(Path(sys.argv[1]))
        except Exception as error:
            result = {"ok": False, "message": str(error)}
        report = updates / "last-result.json"
        staged_report = updates / "last-result.tmp"
        staged_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        staged_report.replace(report)
        if not result["ok"]:
            ctypes.windll.user32.MessageBoxW(
                None, f"{result['message']}\n照片與案件資料保留。\n紀錄：{report}",
                "MatLens 更新未完成", 0x10,
            )
        return 0 if result["ok"] else 1
    finally:
        lock.unlink()  # Only this worker's exclusive lock file, never program/user files.


if __name__ == "__main__":
    raise SystemExit(main())
