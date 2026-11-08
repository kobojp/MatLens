"""Run the packaged worker against an intentionally mismatched QA manifest.

The signed manifest claims a newer version than the supplied real EXE; preflight
must fail, leave the old sentinel/data untouched, and retain detailed log files.
No production installation is used. Never publish this QA manifest.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path

from backend.app.db import initialize
from desktop.update_core import verify_manifest, verify_package
from desktop.version import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(Path("desktop/update-source.json").read_text("utf-8"))
    manifest = verify_manifest(args.manifest.read_bytes(), source["public_key"], "preview")
    verify_package(args.package, manifest)
    assert manifest["version"] != VERSION, "QA must intentionally mismatch the EXE version"
    root = Path(tempfile.mkdtemp(prefix="matlens-failed-update-log-qa-"))
    data = root / "MatLens"
    target = data / "app"
    target.mkdir(parents=True)
    old = target / "MatLens.exe"
    old.write_bytes(b"original-test-program")
    initialize(data / "matlens.db")
    database = (data / "matlens.db").read_bytes()
    photo = data / "photos/original.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"original-test-photo")
    work = data / "updates" / uuid.uuid4().hex
    work.mkdir(parents=True)
    shutil.copy2(args.package, work / "package.zip")
    shutil.copy2(args.manifest, work / "manifest.json")
    # Use a completed test-owned PID, rather than asking the worker to wait on the test runner.
    exited = subprocess.Popen([sys.executable, "-c", "pass"],
                              creationflags=subprocess.CREATE_NO_WINDOW)
    exited.wait(timeout=10)
    (work / "job.json").write_text(json.dumps({"parent_pid": exited.pid, "channel": "preview",
                                               "target": str(target)}), "utf-8")
    env = {**os.environ, "LOCALAPPDATA": str(root)}
    env.pop("MATLENS_DESKTOP_DATA_DIR", None)
    process = subprocess.Popen([str(args.worker.resolve()), str(work / "job.json")],
                               cwd=work, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    report = {"ok": False, "test_root": str(root), "job_id": work.name}
    try:
        deadline = time.monotonic() + 130
        result_path = data / "updates/last-result.json"
        while not result_path.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        result = json.loads(result_path.read_text("utf-8"))
        assert not result["ok"] and result["failed_stage"] == "preflight", result
        probe = json.loads((work / "probe.json").read_text("utf-8"))
        assert probe["ok"] and probe["version"] == VERSION, probe
        log = data / "logs/updates" / work.name / "worker.log"
        entries = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
        failure = next(entry for entry in entries if entry["event"] == "failed")
        assert failure["failed_stage"] == "preflight"
        assert failure["error_type"] and failure["traceback"]
        assert old.read_bytes() == b"original-test-program"
        assert (data / "matlens.db").read_bytes() == database
        assert photo.read_bytes() == b"original-test-photo"
        with closing(sqlite3.connect(data / "backups" / f"before-update-{work.name}.db")) as backup:
            assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        report.update(ok=True, expected_preflight_failure=True, failure=failure,
                      probe_version=probe["version"], claimed_version=manifest["version"],
                      database_preserved=True, photos_preserved=True, old_program_preserved=True,
                      backup_verified=True)
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        if process.poll() is None:
            # Our isolated worker may be waiting in its failure-message dialog.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        process.wait(timeout=15)


if __name__ == "__main__":
    main()
