from __future__ import annotations

import threading
import time

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
        if result.get("ok"):
            # Reload from the page so the existing same-site desktop session is retained.
            window.events.loaded.clear()
            window.evaluate_js("setTimeout(() => location.reload(), 0); true")
            if not window.events.loaded.wait(15):
                raise RuntimeError("Reload did not finish")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                restored = window.evaluate_js(
                    "Boolean(document.querySelector('input[name=storage-subfolder][value=底座]')?.checked"
                    " && document.querySelector('.free-date-toggle input')?.checked === false"
                    " && document.querySelector('.destination-badge')?.textContent.includes('底座')"
                    " && document.querySelector('.workspace.layout-tiles.panel-top.tiles-medium')"
                    " && document.querySelector('#case-editor-fields')?.hidden"
                    " && document.querySelector('.case-table')?.textContent.includes('DESKTOP-QA'))"
                )
                if restored:
                    result["settings_restored_after_reload"] = True
                    result["ui_preferences_restored"] = True
                    break
                time.sleep(0.1)
            else:
                result["reload_state"] = window.evaluate_js(
                    "({radio: document.querySelector("
                    "'input[name=storage-subfolder][value=底座]')?.checked,"
                    "date: document.querySelector('.free-date-toggle input')?.checked,"
                    "badge: document.querySelector('.destination-badge')?.textContent,"
                    "cases: document.querySelector('.case-table')?.textContent,"
                    "error: document.querySelector('[role=alert]')?.textContent,"
                    "text: document.body.innerText.slice(0, 2000), url: location.href,"
                    "html: document.documentElement.outerHTML.slice(0, 3000),"
                    "resources: performance.getEntriesByType('resource').map("
                    "r => ({name:r.name, size:r.transferSize}))})"
                )
                raise RuntimeError("Storage settings were not restored after reload")
            window.resize(1000, 760)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                width = window.evaluate_js("innerWidth")
                if width <= 1000:
                    break
                time.sleep(0.1)
            def wait_ui(expression: str):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if window.evaluate_js(expression):
                        return
                    time.sleep(0.1)
                raise RuntimeError("Narrow UI did not finish applying settings")

            def measure(label: str):
                metrics = window.evaluate_js(
                    "({viewport: innerWidth, document: document.documentElement.scrollWidth})"
                )
                result.setdefault("narrow_layouts", {})[label] = metrics
                if metrics["document"] > metrics["viewport"] + 1:
                    raise RuntimeError(f"Narrow {label} workspace overflows horizontally")

            measure("top_collapsed")
            window.evaluate_js("document.querySelector('.collapse-editor').click(); true")
            wait_ui("!document.querySelector('#case-editor-fields').hidden")
            measure("top_expanded")
            for layout in ["classic", "tiles"]:
                window.evaluate_js("document.querySelector('#tab-settings').click(); true")
                wait_ui("!document.querySelector('#panel-settings').hidden")
                window.evaluate_js(
                    f"document.querySelector('input[name=workspace-layout][value={layout}]')"
                    ".click(); true"
                )
                wait_ui(f"document.querySelector('.workspace.layout-{layout}') !== null")
                if layout == "tiles":
                    window.evaluate_js(
                        "document.querySelector('input[name=case-panel-position][value=right]')"
                        ".click(); document.querySelector('input[name=photo-tile-size]"
                        "[value=large]').click(); true"
                    )
                    wait_ui("document.querySelector('.workspace.panel-right.tiles-large') !== null")
                wait_ui("document.querySelector('.ui-settings .preferences-status')"
                        "?.textContent.includes('已儲存') && !window.matlensDesktopState.saving")
                window.evaluate_js("document.querySelector('#tab-workspace').click(); true")
                wait_ui("!document.querySelector('#panel-workspace').hidden")
                measure(layout)
            # Long paths must wrap/truncate inside the same visible destination bar.
            window.evaluate_js(
                "window.qaOriginalPath = document.querySelector('.storage-bar code').textContent;"
                "document.querySelector('.storage-bar code').textContent = "
                "'測試長路徑/'.repeat(100);"
                "true"
            )
            measure("long_path")
            window.evaluate_js("document.querySelector('.storage-bar code').textContent = "
                               "window.qaOriginalPath; true")
    except Exception as error:
        result.update(ok=False, error=str(error))
    finally:
        # The self-test owns this isolated draft. Suppress dialogs on a failed test.
        draft.update_state(2**53 - 1, False, False)
        window.destroy()
