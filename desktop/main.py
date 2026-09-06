from __future__ import annotations

import argparse
import ctypes
import json
import logging
import multiprocessing
import os
import sys
import tempfile
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.app.main import create_app
from desktop.bridge import DraftState, confirm_close
from desktop.data import migrate_legacy, resource_root, user_data_dir
from desktop.instance import SingleInstance
from desktop.server import running_server


def main() -> int:
    parser = argparse.ArgumentParser(description="MatLens Windows 桌面版")
    parser.add_argument("--import-from", type=Path, help="首次啟動時匯入舊版 matlens.db")
    parser.add_argument("--self-test", action="store_true", help="在獨立暫存目錄驗證桌面流程")
    parser.add_argument("--report", type=Path, help="--self-test 的 JSON 驗證報告路徑")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("桌面版目前支援 Windows 10／11。")
    data_dir = (Path(tempfile.mkdtemp(prefix="matlens-self-test-"))
                if args.self_test else user_data_dir())
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "logs" / "desktop.log"
    log_path.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3,
                                     encoding="utf-8")],
        format="%(asctime)s %(levelname)s %(message)s",
    )
    instance = None
    try:
        instance = SingleInstance(data_dir)
        if instance.already_running:
            return 0
        frontend = resource_root() / "frontend" / "dist"
        if not (frontend / "index.html").is_file():
            raise RuntimeError("前端尚未建置。請先執行 npm --prefix frontend run build。")
        database = data_dir / "matlens.db"
        if args.import_from and database.exists():
            raise RuntimeError("桌面版已有資料，無法覆蓋匯入；請保留兩份資料庫。")
        if args.import_from and not args.import_from.is_file():
            raise RuntimeError("找不到指定的舊版資料庫。")
        legacy_root = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                       else resource_root())
        source = args.import_from or legacy_root / "data" / "matlens.db"
        backup = None if args.self_test else migrate_legacy(source, database)
        if backup:
            logging.info("Imported legacy database; backup: %s", backup)

        import webview

        window = None

        def pick_folder(initial: str) -> str | None:
            selected = window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial)
            return str(selected[0]) if selected else None

        app = create_app(database_path=database, photo_root=data_dir / "photos",
                         frontend_dist=frontend, folder_picker=pick_folder)
        with running_server(app) as url:
            draft = DraftState()
            window = webview.create_window(
                "MatLens — 消防材料更換照片管理", url, width=1440, height=950,
                min_size=(1000, 700), background_color="#f4f6f7",
                js_api=draft,
                hidden=args.self_test,
            )
            stop = threading.Event()

            def may_close() -> bool:
                return confirm_close(draft, window.create_confirmation_dialog)

            def listen_activation():
                while not stop.is_set():
                    if instance.wait_activation():
                        window.restore()
                        window.show()

            window.events.closing += may_close
            watcher = threading.Thread(target=listen_activation, daemon=True)
            watcher.start()
            result = {}
            try:
                if args.self_test:
                    from desktop.diagnostics import exercise_window

                    webview.start(
                        exercise_window, (window, draft, result, threading.Event()),
                        gui="edgechromium", private_mode=True,
                    )
                else:
                    webview.start(gui="edgechromium", private_mode=True)
            finally:
                stop.set()
                watcher.join(timeout=2)
        if args.self_test:
            from contextlib import closing

            from backend.app.db import connect

            with closing(connect(database)) as db:
                result["persisted_cases"] = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
                result["persisted_photos"] = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            result["data_dir"] = str(data_dir)
            result["ok"] = bool(result.get("ok") and result["persisted_cases"] == 1
                                and result["persisted_photos"] == 3)
            report = args.report or data_dir / "report.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0 if result["ok"] else 1
        return 0
    except Exception as error:
        logging.exception("Desktop startup/runtime failed")
        ctypes.windll.user32.MessageBoxW(
            None, f"{error}\n\n請確認已安裝 Microsoft Edge WebView2 Runtime。\n紀錄：{log_path}",
            "MatLens 無法啟動", 0x10,
        )
        return 1
    finally:
        if instance:
            instance.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
