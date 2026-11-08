"""QA-only entry: freeze with an archived old checkout, never ship this entry.

The original UI, bridge, version, update service and installed worker are retained.
UI automation is injected. Transport can use signed local fixtures or original HTTPS.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import sys
import threading
from pathlib import Path

import webview

from desktop import main, updates
from desktop.bridge import DesktopBridge


def run():
    fixture = json.loads(Path(os.environ["MATLENS_QA_FIXTURE"]).read_text("utf-8"))
    trace = Path(fixture["trace"])
    events = []

    def record(self, event):
        events.append({**event, "qa_executable": sys.executable})
        trace.write_text(json.dumps(events, ensure_ascii=False, indent=2), "utf-8")

    DesktopBridge.qa_event = record

    def local_transport(url, target, limit, progress=lambda count: None):
        source = Path(fixture["urls"][url])  # Reject unexpected URLs; no network fallback.
        if source.stat().st_size > limit:
            raise ValueError("QA fixture exceeds original download bound")
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        progress(source.stat().st_size)

    if not fixture.get("live_download", False):
        updates.download = local_transport
    create = webview.create_window

    def hidden_window(*args, **kwargs):
        kwargs["hidden"] = True
        return create(*args, **kwargs)

    webview.create_window = hidden_window
    start = webview.start

    def exercise(*_args, **_kwargs):
        window = webview.windows[0]
        finished = threading.Event()

        def callback(result):
            if result.get("error"):
                record(None, result)
                window.destroy()
            finished.set()

        if not window.events.loaded.wait(30):
            record(None, {"error": "Old client did not load"})
            window.destroy()
            return
        window.evaluate_js("""
        (async () => {
          const wait = async (check, label) => {
            for (let i = 0; i < 300; i++) {
              if (await check()) return;
              await new Promise(resolve => setTimeout(resolve, 100));
            }
            throw new Error(label);
          };
          try {
            await wait(() => window.pywebview?.api.qa_event &&
              document.querySelector('.update-section > button'), 'Old update panel');
            const api = window.pywebview.api;
            await wait(async () => (await api.update_status()).phase === 'available',
              'Check update');
            const before = await api.update_status();
            await api.qa_event({stage:'before', status:before});
            document.querySelector('.update-section > button').click();
            const button = text => [...document.querySelectorAll('button')]
              .find(node => node.textContent === text);
            await wait(() => button('下載更新'), 'Download button');
            button('下載更新').click();
            await wait(async () => (await api.update_status()).phase === 'ready', 'Download ready');
            await wait(() => button('安裝並重新啟動'), 'Install button');
            await api.qa_event({stage:'ready', status:await api.update_status(),
              draft:window.matlensDesktopState});
            window.confirm = () => true;
            button('安裝並重新啟動').click();
            await wait(async () => (await api.update_status()).phase === 'installing', 'Handoff');
            await api.qa_event({stage:'installing', status:await api.update_status()});
            return {ok:true};
          } catch(error) { return {error:String(error), text:document.body.innerText}; }
        })()
        """, callback=callback)
        if not finished.wait(100):
            record(None, {"error": "Old client flow timed out"})
            window.destroy()

    def qa_start(*args, **kwargs):
        return start(exercise, gui="edgechromium", private_mode=True)

    webview.start = qa_start
    return main.main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(run())
