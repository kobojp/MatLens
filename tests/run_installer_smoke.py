"""Compile a QA identity, install twice, inspect shortcuts, then uninstall.

All files and shortcuts stay in a new temporary root. The QA uninstall entry is
separate from MatLens. No production installation or database is touched.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path

from backend.app.db import initialize
from desktop.instance import SingleInstance
from desktop.version import VERSION


def run(command: list[str], *, success: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=180)
    if success and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}\n"
                           + result.stdout.decode("utf-8", errors="replace")[-3000:])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    root = Path(tempfile.mkdtemp(prefix="matlens-installer-qa-")) / "安裝測試"
    root.mkdir()
    data = root / "MatLens"
    initialize(data / "matlens.db")
    with closing(sqlite3.connect(data / "matlens.db")) as database, database:
        database.execute("INSERT INTO custom_options VALUES (?, ?, ?, ?)",
                         (1, "material", "既有清冊", "2026-10-19"))
    sentinels = {data / "matlens.db": (data / "matlens.db").read_bytes()}
    for name in ["photos/原始照片.jpg", "backups/保留.db", "logs/保留.log", "updates/保留.txt"]:
        path = data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"never-change")
        sentinels[path] = path.read_bytes()
    run([str(args.compiler.resolve()), f"/DSmokeRoot={root}", f"/O{root}",
         str(repository / "packaging/MatLens.iss")])
    setup = root / "MatLens-Setup-Smoke.exe"
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=desktopicon"]
    guard = SingleInstance(data)
    try:
        blocked = run([*command, f"/LOG={root / 'running-blocked.log'}"], success=False)
        assert blocked.returncode != 0, "Installer must refuse an open MatLens, including legacy"
        assert not (data / "app/MatLens.exe").exists()
    finally:
        guard.close()
    lock = data / "updates/install.lock"
    lock.write_text("test-only-lock", "utf-8")
    try:
        assert run(command, success=False).returncode != 0
    finally:
        lock.unlink()  # Exact test-owned marker in this isolated root.
    for attempt in ["install", "upgrade"]:
        run([*command, f"/LOG={root / (attempt + '.log')}"])
        assert (data / "app/MatLens.exe").is_file()
        assert (data / "app/MatLensUpdater.exe").is_file()
        assert not (data / "app/matlens.db").exists()
        for path, content in sentinels.items():
            assert path.read_bytes() == content
        for kind in ["Desktop", "Programs"]:
            shortcut = root / "shortcuts" / kind / "MatLens.lnk"
            assert shortcut.is_file()
            # The shortcut parser reads this QA file only; no interactive UI is opened.
            script = ("[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; "
                      "$shell = New-Object -ComObject WScript.Shell; "
                      "$s = $shell.CreateShortcut($env:MATLENS_QA_LINK); "
                      "$s.TargetPath")
            environment = os.environ.copy()
            environment["MATLENS_QA_LINK"] = str(shortcut)
            target = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", script], env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            assert Path(target.decode("utf-8").strip()) == data / "app/MatLens.exe"
    exe_report = root / "installed-exe.json"
    run([str(data / "app/MatLens.exe"), "--self-test", "--report", str(exe_report)])
    result = json.loads(exe_report.read_text("utf-8"))
    assert result["ok"] and result["version"] == VERSION
    assert result["database_location"]
    run([str(data / "uninstall/unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
    deadline = time.monotonic() + 15
    while (data / "app/MatLens.exe").exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not (data / "app/MatLens.exe").exists()
    assert not list((root / "shortcuts").rglob("*.lnk"))
    for path, content in sentinels.items():
        assert path.read_bytes() == content
    report = {"ok": True, "version": VERSION, "test_root": str(root),
              "running_app_blocked": True, "online_update_blocked": True,
              "install_upgrade_verified": True, "shortcuts_verified": True,
              "uninstall_data_preserved": True, "exe_self_test": result}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
