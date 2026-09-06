"""Real WebView2 integration test. Run: uv run --locked python -m tests.run_desktop_smoke."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path

import webview

from backend.app.main import create_app
from desktop.bridge import DraftState
from desktop.data import resource_root
from desktop.server import running_server


def main():
    # Keep evidence under TEMP, outside the user's cases and photo directories.
    data = Path(tempfile.mkdtemp(prefix="matlens-webview-test-"))
    app = create_app(database_path=data / "matlens.db", photo_root=data / "photos",
                     frontend_dist=resource_root() / "frontend" / "dist")
    result = {}
    completed = threading.Event()
    with running_server(app) as url:
        window = webview.create_window("MatLens integration test", url, hidden=True,
                                       js_api=DraftState())

        def callback(value):
            result.update(value)
            completed.set()

        def exercise():
            try:
                if not window.events.loaded.wait(15):
                    raise RuntimeError("WebView2 did not load")
                script = (resource_root() / "desktop" / "smoke.js").read_text(encoding="utf-8")
                window.evaluate_js(script, callback=callback)
                if not completed.wait(40):
                    result.update(ok=False, error="WebView2 flow timed out")
            except Exception as error:
                result.update(ok=False, error=str(error))
            finally:
                window.destroy()

        webview.start(exercise, gui="edgechromium", private_mode=True)
    with closing(sqlite3.connect(data / "matlens.db")) as db:
        result["persisted_cases"] = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        result["persisted_photos"] = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    result["data_dir"] = str(data)
    print(json.dumps(result, ensure_ascii=False))
    assert result.get("ok") and result["persisted_cases"] == 1 and result["persisted_photos"] == 3


if __name__ == "__main__":
    main()
