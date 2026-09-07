"""Exercise the real worker with packaged EXE in an isolated LOCALAPPDATA.

uv run --locked python -m tests.run_update_smoke --package ... --manifest ...
Only the old worker version is simulated (0.3.0); network, UI safety and failures
are covered separately. No production installation/database is written.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

from backend.app.db import initialize
from desktop import updater


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--helper", type=Path, help="Test-only frozen 0.3.0 updater")
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="matlens-update-qa-"))
    os.environ["LOCALAPPDATA"] = str(root)
    os.environ.pop("MATLENS_DESKTOP_DATA_DIR", None)
    target = root / "Programs" / "MatLens"
    target.mkdir(parents=True)
    (target / "MatLens.exe").write_bytes(b"old-program-sentinel")
    data = root / "MatLens"
    initialize(data / "matlens.db")
    with closing(sqlite3.connect(data / "matlens.db")) as db, db:
        db.execute("INSERT INTO custom_options VALUES (1, 'material', '保留材料', '2026-09-07')")
    photos = root / "使用者照片" / "9月" / "底座"
    photos.mkdir(parents=True)
    original = photos / "original.jpg"
    original.write_bytes(b"original-must-not-change")
    work = data / "updates" / uuid.uuid4().hex
    work.mkdir(parents=True)
    shutil.copy2(args.package, work / "package.zip")
    shutil.copy2(args.manifest, work / "manifest.json")
    parent = subprocess.Popen([sys.executable, "-c", "pass"],
                              creationflags=subprocess.CREATE_NO_WINDOW)
    parent.wait(timeout=10)
    job = work / "job.json"
    job.write_text(json.dumps({"parent_pid": parent.pid, "channel": "stable"}), "utf-8")
    # Baseline updater version is the sole compatibility simulation.
    updater.VERSION = "0.2.0"
    launched = []
    original_popen = subprocess.Popen

    def recording_popen(*values, **kwargs):
        process = original_popen(*values, **kwargs)
        launched.append(process)
        return process

    updater.subprocess.Popen = recording_popen
    try:
        if args.helper:
            subprocess.run([str(args.helper.resolve()), str(job)], cwd=work,
                           timeout=150, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            result = json.loads((data / "updates" / "last-result.json").read_text("utf-8"))
        else:
            result = updater.apply_update(job)
        with closing(sqlite3.connect(data / "matlens.db")) as db:
            assert db.execute("SELECT value FROM custom_options").fetchone()[0] == "保留材料"
        with closing(sqlite3.connect(result["backup"])) as db:
            assert db.execute("SELECT value FROM custom_options").fetchone()[0] == "保留材料"
        assert original.read_bytes() == b"original-must-not-change"
        assert (Path(result["previous"]) / "MatLens.exe").read_bytes() == b"old-program-sentinel"
        result.update(sqlite_preserved=True, photos_preserved=True, backup_verified=True,
                      startup_verified=True, old_worker_version_simulated=True, test_root=str(root),
                      frozen_worker=bool(args.helper))
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        updater.subprocess.Popen = original_popen
        for process in launched:
            if process.poll() is None:
                # Test-owned process and isolated clean database; no user draft can be present.
                process.terminate()
                process.wait(timeout=15)
        if args.helper and (work / "startup.json").exists():
            from ctypes import wintypes

            pid = json.loads((work / "startup.json").read_text("utf-8")).get("pid")
            if pid:
                api = ctypes.WinDLL("kernel32", use_last_error=True)
                api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                api.OpenProcess.restype = wintypes.HANDLE
                api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                api.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = api.OpenProcess(1, False, pid)
                if handle:
                    api.TerminateProcess(handle, 0)
                    api.CloseHandle(handle)


if __name__ == "__main__":
    main()
