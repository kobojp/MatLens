from __future__ import annotations

import secrets
import socket
import threading
import time
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse


def protect_app(app: FastAPI, token: str, origin: str) -> None:
    cookie = "matlens_desktop"

    @app.middleware("http")
    async def desktop_session(request: Request, call_next):
        if request.headers.get("host") != origin.removeprefix("http://"):
            return JSONResponse({"detail": "Invalid host"}, status_code=403)
        request_origin = request.headers.get("origin")
        if request_origin and request_origin != origin:
            return JSONResponse({"detail": "Invalid origin"}, status_code=403)
        if request.url.path == "/" and secrets.compare_digest(
            request.query_params.get("desktop_token", ""), token
        ):
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(cookie, token, httponly=True, samesite="strict")
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        if not secrets.compare_digest(request.cookies.get(cookie, ""), token):
            return JSONResponse({"detail": "Desktop session required"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        return response


@contextmanager
def running_server(app: FastAPI):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
        token = secrets.token_urlsafe(32)
        protect_app(app, token, origin)
        server = uvicorn.Server(uvicorn.Config(
            app, log_config=None, access_log=False, loop="asyncio", http="h11",
            ws="none", timeout_graceful_shutdown=30,
        ))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("MatLens 本機服務無法啟動。")
                time.sleep(0.05)
            yield f"{origin}/?desktop_token={token}"
        finally:
            server.should_exit = True
            thread.join(timeout=35)
            if thread.is_alive():
                raise RuntimeError("本機服務尚未完成關閉，請查看紀錄。")
