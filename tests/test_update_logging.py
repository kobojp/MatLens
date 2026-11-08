from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from desktop.bridge import DesktopBridge
from desktop.updates import UpdateService
from tests.test_updates import settled, signed_manifest


def read_events(root: Path, job_id: str, source: str = "client"):
    path = root / "logs/updates" / job_id / f"{source}.log"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_check_failure_logs_stage_traceback_and_survives_restart(tmp_path, monkeypatch):
    service = UpdateService(tmp_path)

    def offline(*args):
        raise OSError("network down https://example.com/a?token=SECRET")

    monkeypatch.setattr("desktop.updates.download", offline)
    service.check()
    state = settled(service)
    events = read_events(tmp_path, state["job_id"])
    failure = events[-1]
    assert failure["event"] == "failed"
    assert failure["failed_stage"] == "check.download_manifest"
    assert failure["error_type"] == "OSError"
    assert "network down" in failure["traceback"]
    assert "SECRET" not in json.dumps(events)
    assert failure["current"] == state["current"]
    assert failure["executable"] == state["executable"]
    assert failure["time"] and failure["pid"] > 0
    UpdateService(tmp_path)
    assert read_events(tmp_path, state["job_id"]) == events


def test_corrupt_package_logs_target_version_and_verification_stage(tmp_path, monkeypatch):
    raw, public = signed_manifest()
    service = UpdateService(tmp_path)
    service._source = {"public_key": public, "stable": "https://example.com/stable.json"}
    service._state["installable"] = True

    def fetch(url, target, limit, progress=lambda count: None):
        target.write_bytes(raw if target.name == "manifest.json" else b"corrupt")

    monkeypatch.setattr("desktop.updates.download", fetch)
    service.check()
    settled(service)
    service.fetch_package()
    state = settled(service)
    failure = read_events(tmp_path, state["job_id"])[-1]
    assert failure["failed_stage"] == "download.verify_package"
    assert failure["version"] == state["version"]
    assert failure["error_type"] == "ValueError"


def test_bridge_opens_only_fixed_update_log_folder_and_reports_failure(tmp_path, monkeypatch):
    calls = []
    service = UpdateService(tmp_path)
    bridge = DesktopBridge(service, lambda: None)
    monkeypatch.setattr("desktop.updates.subprocess.Popen", lambda args: calls.append(args))
    assert bridge.open_update_logs()["ok"]
    assert calls == [["explorer.exe", str((tmp_path / "logs/updates").resolve())]]

    def fail(args):
        raise OSError("Explorer unavailable")

    monkeypatch.setattr("desktop.updates.subprocess.Popen", fail)
    assert "無法開啟" in bridge.open_update_logs()["error"]


def test_log_write_failure_is_visible_and_does_not_break_update_check(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.write_text("test blocks directory", "utf-8")
    service = UpdateService(tmp_path)
    raw, public = signed_manifest()
    service._source = {"public_key": public, "stable": "https://example.com/stable.json"}
    monkeypatch.setattr("desktop.updates.download",
                        lambda url, target, limit: target.write_bytes(raw))
    service.check()
    state = settled(service)
    assert state["phase"] == "available"
    assert "無法寫入更新紀錄" in state["log_error"]


@pytest.mark.skipif(os.name != "nt", reason="Windows worker error dialog")
def test_worker_logs_invalid_job_before_progress_file_exists(tmp_path, monkeypatch):
    from desktop import updater

    monkeypatch.setattr(updater, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("sys.argv", ["worker", str(tmp_path / "untrusted/job.json")])
    monkeypatch.setattr(updater.ctypes.windll.user32, "MessageBoxW", lambda *args: 1)
    assert updater.main() == 1
    paths = list((tmp_path / "logs/updates").glob("*/worker.log"))
    assert len(paths) == 1
    entries = [json.loads(line) for line in paths[0].read_text("utf-8").splitlines()]
    failure = next(entry for entry in entries if entry["event"] == "failed")
    assert failure["failed_stage"] == "validate_or_prepare_job"
    assert failure["error_type"] == "ValueError" and failure["traceback"]
