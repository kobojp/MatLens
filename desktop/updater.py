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
from datetime import UTC, datetime
from pathlib import Path

from desktop.data import resource_root, user_data_dir
from desktop.installation import program_directories, validate_program_directory
from desktop.update_core import extract_package, verify_manifest, verify_package, version_key
from desktop.update_log import clean_text, clean_values, record_event
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
                if (result.get("ok") and result.get("version") == version
                        and result.get("pid") == process.pid
                        and Path(result.get("executable", "")).resolve()
                        == (target / "MatLens.exe").resolve()):
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


def validated_job(job: Path) -> tuple[Path, Path]:
    data = user_data_dir().resolve()
    work = job.resolve().parent
    updates = data / "updates"
    if (work.parent != updates or not len(work.name) == 32
            or any(c not in "0123456789abcdef" for c in work.name)
            or job.name != "job.json"):
        raise ValueError("更新工作目錄不正確。")
    return data, work


def apply_update(job: Path):
    data, work = validated_job(job)
    state = {"job_id": work.name, "current": VERSION}

    def progress(stage: str, *, failure: BaseException | None = None, **values):
        state.update(stage=stage, at=datetime.now(UTC).isoformat(), **values)
        warning = record_event(data, work.name, "worker", stage, error=failure,
                               **{key: value for key, value in state.items()
                                  if key not in {"job_id", "current", "stage", "at"}})
        if warning:
            state["log_error"] = warning
        staged = work / "progress.tmp"
        staged.write_text(json.dumps(clean_values(state), ensure_ascii=False, indent=2), "utf-8")
        staged.replace(work / "progress.json")

    progress("verify")
    try:
        return _apply_update(job, data, work, progress)
    except Exception as error:
        stage = state["stage"]
        if stage == "preflight":
            reason = ""
            probe = work / "probe.json"
            if probe.exists():
                try:
                    reason = str(json.loads(probe.read_text("utf-8")).get("error", ""))[:300]
                except (ValueError, OSError, AttributeError):
                    reason = "無法讀取新版自測報告"
            if isinstance(error, subprocess.TimeoutExpired):
                reason = "自測程序逾時"
            message = "新版預先測試失敗，未替換程式。" + (f"原因：{reason}" if reason else "")
        elif stage == "startup":
            message = "新版啟動檢查失敗，已嘗試回復原程式；請核對更新診斷。"
        else:
            labels = {"verify": "驗證更新", "wait": "等待程式關閉", "backup": "備份資料庫",
                      "prepare": "準備程式檔案", "replace": "替換程式檔案"}
            message = f"{labels.get(stage, stage)}未完成：{error}"
        message = clean_text(message)
        progress("failed", failure=error, failed_stage=stage, message=message,
                 detail=clean_text(repr(error)))
        if stage == "verify" and isinstance(error, ValueError):
            raise
        raise RuntimeError(message) from error


def _apply_update(job: Path, data: Path, work: Path, progress):
    params = json.loads(job.read_text(encoding="utf-8"))
    # Older apps omit target and always live in the legacy location.
    target = validate_program_directory(Path(params.get("target", program_directories()[1])))
    # Reject junctions/symlinks: never rename a redirected installation or user data.
    if target.resolve() != target.absolute() or not (target / "MatLens.exe").is_file():
        raise ValueError("安裝位置不正確，停止更新。")
    allowed = {"matlens.exe", "matlensupdater.exe", "_internal"}
    if any(child.name.lower() not in allowed for child in target.iterdir()):
        raise ValueError("安裝目錄含非程式檔案，為保護資料已停止自動更新。")
    pid = params["parent_pid"]
    if type(pid) is not int or pid <= 0 or pid == os.getpid():
        raise ValueError("主程式識別碼不正確。")
    source = json.loads((resource_root() / "desktop" / "update-source.json").read_text("utf-8"))
    manifest = verify_manifest((work / "manifest.json").read_bytes(),
                               source["public_key"], params["channel"])
    if version_key(manifest["version"]) <= version_key(VERSION):
        raise ValueError("拒絕安裝相同或較舊版本。")
    verify_package(work / "package.zip", manifest)
    progress("wait", version=manifest["version"], target=str(target))
    wait_for_parent(pid)
    from desktop.instance import SingleInstance

    guard = SingleInstance(data)
    if guard.already_running:
        guard.close()
        raise RuntimeError("MatLens 仍在執行，停止更新。")
    try:
        progress("backup")
        backup = data / "backups" / f"before-update-{work.name}.db"
        backup_database(data / "matlens.db", backup)
        unpacked = extract_package(work / "package.zip", work / "unpacked")
        # Real WebView2 + save/reload flow against an isolated temporary database.
        probe = work / "probe.json"
        progress("preflight")
        subprocess.run([str(unpacked / "MatLens.exe"), "--self-test", "--report", str(probe)],
                       cwd=unpacked, timeout=90, check=True)
        probe_result = json.loads(probe.read_text("utf-8"))
        if not probe_result.get("ok") or probe_result.get("version") != manifest["version"]:
            raise RuntimeError("新版預先測試失敗，未替換程式。")
        suffix = uuid.uuid4().hex
        progress("prepare")
        prepared = target.with_name(f"{target.name}.next-{suffix}")
        previous = target.with_name(f"{target.name}.previous-{suffix}")
        if prepared.resolve().parent != target.resolve().parent:
            raise ValueError("暫存安裝位置不正確。")
        shutil.copytree(unpacked, prepared)
        journal = {"target": str(target), "previous": str(previous), "prepared": str(prepared),
                   "backup": str(backup), "version": manifest["version"], "job_id": work.name}
        (work / "recovery.json").write_text(json.dumps(journal), encoding="utf-8")
    finally:
        guard.close()
    # New app needs the instance mutex. Update lock below prevents overlapping workers.
    def start(folder):
        progress("startup")
        start_and_check(folder, work / "startup.json", manifest["version"])

    progress("replace")
    try:
        swap_program(target, prepared, previous, start)
    except Exception as error:
        record_event(data, work.name, "worker", "rollback.state", error=error,
                     target_exists=target.is_dir(), previous_exists=previous.exists(),
                     prepared_exists=prepared.exists())
        raise
    progress("complete", message=f"已更新至 {manifest['version']}。")
    return {"ok": True, "message": f"已更新至 {manifest['version']}。", **journal}


def main() -> int:
    updates = user_data_dir() / "updates"
    requested_id = Path(sys.argv[1]).parent.name if len(sys.argv) > 1 else ""
    job_id = (requested_id if len(requested_id) == 32
              and all(char in "0123456789abcdef" for char in requested_id) else uuid.uuid4().hex)
    record_event(updates.parent, job_id, "worker", "worker.start")
    try:
        updates.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        record_event(updates.parent, job_id, "worker", "failed", error=error,
                     failed_stage="prepare_work_directory")
        return 1
    lock = updates / "install.lock"
    try:
        with lock.open("x", encoding="utf-8") as output:
            output.write(str(os.getpid()))
    except FileExistsError:
        record_event(updates.parent, job_id, "worker", "lock.busy",
                     message="已有更新工作或殘留更新鎖，未開始替換程式。")
        return 1
    except OSError as error:
        record_event(updates.parent, job_id, "worker", "failed", error=error,
                     failed_stage="acquire_lock")
        return 1
    try:
        try:
            result = apply_update(Path(sys.argv[1]))
        except Exception as error:
            details = {}
            try:
                _, work = validated_job(Path(sys.argv[1]))
                details = json.loads((work / "progress.json").read_text("utf-8"))
            except (OSError, ValueError, IndexError):
                pass
            if not details:
                record_event(updates.parent, job_id, "worker", "failed", error=error,
                             failed_stage="validate_or_prepare_job")
            result = {**details, "ok": False, "message": details.get("message", str(error)),
                      "job_id": Path(sys.argv[1]).parent.name if len(sys.argv) > 1 else ""}
        report = updates / "last-result.json"
        staged_report = updates / "last-result.tmp"
        try:
            staged_report.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
            staged_report.replace(report)
        except OSError as error:
            record_event(updates.parent, job_id, "worker", "failed", error=error,
                         failed_stage="save_result")
            return 1
        record_event(updates.parent, job_id, "worker",
                     "result.saved", ok=result["ok"], message=result["message"])
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
