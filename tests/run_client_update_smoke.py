"""Old complete UI -> original worker -> signed new EXE, in isolated LOCALAPPDATA.

qa-client must be frozen from archived baseline source with qa_update_client.py.
The baseline UI and worker must be from its verified public signed package.
Transport defaults to a local fixture; --live-download retains original HTTPS.
This does not replace verification on the computer that failed.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from desktop.update_core import download, verify_manifest, verify_package
from tests.test_api import create_case


def stop_owned_process(pid: int, executable: Path):
    """Never terminate a reused PID or a process outside this test installation."""
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                             wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000 | 0x100000 | 1, False, pid)
    if not handle:
        return
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            if Path(buffer.value).resolve() == executable.resolve():
                api.TerminateProcess(handle, 0)
                api.WaitForSingleObject(handle, 15000)
    finally:
        api.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-client", type=Path, required=True)
    parser.add_argument("--original-worker", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline-version", default="0.5.5")
    parser.add_argument("--live-download", action="store_true",
                        help="Keep the old client's genuine HTTPS download implementation")
    parser.add_argument("--require-startup-log", action="store_true")
    parser.add_argument("--layout", choices=["legacy", "installed"], required=True)
    args = parser.parse_args()
    source = json.loads(Path("desktop/update-source.json").read_text("utf-8"))
    manifest = verify_manifest(args.manifest.read_bytes(), source["public_key"], "stable")
    verify_package(args.package, manifest)
    root = Path(tempfile.mkdtemp(prefix="matlens-client-update-qa-"))
    if args.live_download:
        metadata = root / "public-stable.json"
        download(source["stable"], metadata, 128 * 1024)
        public = verify_manifest(metadata.read_bytes(), source["public_key"], "stable")
        assert public == manifest, "Public stable changed; do not test a different target silently"
    data = root / "MatLens"
    target = root / ("MatLens/app" if args.layout == "installed" else "Programs/MatLens")
    shutil.copytree(args.qa_client.resolve(), target)
    shutil.copy2(args.original_worker.resolve(), target / "MatLensUpdater.exe")
    photos = data / "photos"
    (photos / "8月/底座").mkdir(parents=True)
    client = TestClient(create_app(database_path=data / "matlens.db", photo_root=photos))
    response = create_case(client, [(80, 10, 10), (10, 80, 10), (10, 10, 80)])
    assert response.status_code == 201, response.text
    before = client.get(f"/api/cases/{response.json()['id']}").json()
    hashes = {str(path.relative_to(photos)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in photos.rglob("*.jpg")}
    fixture = root / "fixture.json"
    trace = root / "ui-trace.json"
    fixture.write_text(json.dumps({"trace": str(trace), "live_download": args.live_download,
                                  "urls": {
        source["stable"]: str(args.manifest.resolve()),
        manifest["url"]: str(args.package.resolve()),
    }}), "utf-8")
    env = {**os.environ, "LOCALAPPDATA": str(root), "MATLENS_QA_FIXTURE": str(fixture)}
    env.pop("MATLENS_DESKTOP_DATA_DIR", None)
    process = subprocess.Popen([str(target / "MatLens.exe")], cwd=target, env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    startup_pid = None
    transport = "original HTTPS transport" if args.live_download else "local transport"
    report = {"ok": False, "test_root": str(root), "layout": args.layout,
              "boundary": "Archived old source + public UI + original worker; QA entry; "
                          + transport}
    try:
        deadline = time.monotonic() + 180
        result_path = data / "updates/last-result.json"
        while time.monotonic() < deadline:
            if result_path.exists():
                result = json.loads(result_path.read_text("utf-8"))
                break
            if trace.exists():
                if any("error" in event for event in json.loads(trace.read_text("utf-8"))):
                    raise RuntimeError("Old UI flow failed; inspect ui-trace.json")
            time.sleep(0.2)
        else:
            raise RuntimeError("Client update did not finish; inspect isolated updates directory")
        report["result"] = result
        assert result["ok"], result
        if result.get("job_id"):
            work = data / "updates" / result["job_id"]
        else:
            # 0.5.4's genuine worker predates job_id in last-result.json.
            jobs = list((data / "updates").glob("*/job.json"))
            assert len(jobs) == 1, "Ambiguous old-worker job; cannot correlate startup"
            work = jobs[0].parent
        report["correlation_job_id"] = work.name
        startup = json.loads((work / "startup.json").read_text("utf-8"))
        startup_pid = startup["pid"]
        assert startup["version"] == manifest["version"]
        assert Path(startup["executable"]) == target / "MatLens.exe"
        if args.require_startup_log:
            entries = [json.loads(line) for line in
                       (data / "logs/updates" / work.name / "startup.log")
                       .read_text("utf-8").splitlines()]
            assert any(entry["event"] == "startup.ready" for entry in entries)
            report["startup_log_verified"] = True
        events = json.loads(trace.read_text("utf-8"))
        old_event = next(event for event in events if event.get("stage") == "before")
        old = old_event["status"]
        assert old["current"] == args.baseline_version
        assert old["installable"] is True
        assert Path(old.get("executable") or old_event["qa_executable"]) == target / "MatLens.exe"
        assert {event.get("stage") for event in events} >= {"before", "ready", "installing"}
        assert process.wait(timeout=10) == 0
        assert client.get(f"/api/cases/{before['id']}").json() == before
        assert hashes == {
            str(path.relative_to(photos)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in photos.rglob("*.jpg")
        }
        with closing(sqlite3.connect(result["backup"])) as backup:
            assert backup.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
            assert backup.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 3
        report.update(ok=True, before=old, after=startup, ui_events=events,
                      photos_preserved=True, sqlite_preserved=True, backup_verified=True,
                      original_worker_sha256=hashlib.sha256(args.original_worker.read_bytes()).hexdigest())
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        if process.poll() is None:
            process.terminate()  # This test-owned isolated client only.
            process.wait(timeout=15)
        if startup_pid:
            stop_owned_process(startup_pid, target / "MatLens.exe")


if __name__ == "__main__":
    main()
