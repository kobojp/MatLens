from __future__ import annotations

import threading

from desktop.data import resource_root


def exercise_window(window, draft, result: dict, finished: threading.Event) -> None:
    def callback(value):
        result.update(value)
        finished.set()

    try:
        if not window.events.loaded.wait(15):
            raise RuntimeError("WebView2 did not load")
        script = (resource_root() / "desktop" / "smoke.js").read_text(encoding="utf-8")
        window.evaluate_js(script, callback=callback)
        if not finished.wait(40):
            snapshot = window.evaluate_js(
                "({step: window.matlensSmokeStep, visibility: document.visibilityState, "
                "thumbnails: document.querySelectorAll('.thumbnail-item').length})"
            )
            result.update(ok=False, error="WebView2 flow timed out", snapshot=snapshot)
    except Exception as error:
        result.update(ok=False, error=str(error))
    finally:
        # The self-test owns this isolated draft. Suppress dialogs on a failed test.
        draft.update_state(2**53 - 1, False, False)
        window.destroy()
