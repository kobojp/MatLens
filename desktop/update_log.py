"""Append local update events; each job/process role has a separate file."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from desktop.version import VERSION

_lock = threading.Lock()


def clean_text(value: str) -> str:
    def clean_url(match):
        try:
            parts = urlsplit(match.group())
        except ValueError:
            return "<invalid-url>"
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path,
                           "<hidden>" if parts.query else "", ""))

    value = re.sub(r"https?://[^\s'\"<>]+", clean_url, value)
    value = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <hidden>", value)
    return re.sub(r"(?i)(\b(?:token|password|secret|api_key|desktop_token)\s*=\s*)[^\s,'\"&]+",
                  r"\1<hidden>", value)


def clean_values(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        return {key: clean_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_values(item) for item in value]
    return value


def record_event(data: Path, job_id: str, source: str, event: str,
                 *, error: BaseException | None = None, **details) -> str | None:
    """Return a visible warning on failure, while preserving normal update behavior."""
    try:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id) or source not in {
            "client", "worker", "startup",
        }:
            raise ValueError("Invalid update log identifier")
        folder = data.resolve() / "logs" / "updates" / job_id
        if folder.resolve() != folder.absolute():
            raise ValueError("Update log directory must not be redirected")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{source}.log"
        if path.resolve() != path.absolute():
            raise ValueError("Update log file must not be redirected")
        entry = {"time": datetime.now(UTC).isoformat(), "job_id": job_id,
                 "source": source, "event": event, "pid": os.getpid(), "current": VERSION,
                 "executable": str(Path(sys.executable).resolve()), **details}
        if error is not None:
            entry.update(error_type=type(error).__name__, error=str(error),
                         traceback="".join(traceback.format_exception(error))[-16000:])
        # Only metadata supplied here is written: never database/photo contents or headers.
        line = json.dumps(clean_values(entry), ensure_ascii=False, default=str) + "\n"
        with _lock, path.open("a", encoding="utf-8") as output:
            output.write(line)
            output.flush()
        return None
    except (OSError, ValueError) as failure:
        warning = f"無法寫入更新紀錄（{type(failure).__name__}），請檢查資料夾權限與磁碟空間。"
        logging.error(warning)
        return warning
