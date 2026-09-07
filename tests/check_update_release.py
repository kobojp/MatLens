"""Read-only public release smoke test; downloads only to a fresh temporary folder."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from desktop.update_core import download, verify_package
from desktop.updates import UpdateService
from desktop.version import VERSION


def main():
    root = Path(tempfile.mkdtemp(prefix="matlens-public-update-qa-"))
    service = UpdateService(root)
    service.check()
    deadline = time.monotonic() + 45
    while service.status()["phase"] == "checking" and time.monotonic() < deadline:
        time.sleep(0.2)
    state = service.status()
    if state["phase"] != "current" or state["version"] != VERSION:
        raise RuntimeError(state)
    manifest = service._manifest
    target = root / "public-package.zip"
    download(manifest["url"], target, manifest["size"])
    verify_package(target, manifest)
    result = {"ok": True, "version": state["version"], "size": target.stat().st_size,
              "signature_verified": True, "sha256_verified": True, "test_root": str(root)}
    (root / "report.json").write_text(json.dumps(result), "utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
