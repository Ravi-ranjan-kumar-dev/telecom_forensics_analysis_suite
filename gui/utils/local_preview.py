"""Serve only explicitly registered HTML previews over loopback HTTP."""
from __future__ import annotations

import atexit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
from threading import Lock, Thread
import webbrowser

_routes: dict[str, Path] = {}
_lock = Lock()
_server = None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] != "127.0.0.1":
            self.send_error(403)
            return
        with _lock:
            path = _routes.get(self.path)
        if path is None or not path.is_file():
            self.send_error(404)
            return
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


def preview_url(path: str | Path) -> str:
    global _server
    file = Path(path).resolve(strict=True)
    if file.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Only generated HTML previews can be served.")
    with _lock:
        if _server is None:
            _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            _server.daemon_threads = True
            Thread(target=_server.serve_forever, daemon=True, name="EthicalArmor-preview").start()
            atexit.register(_server.server_close)
        token = "/" + secrets.token_urlsafe(32)
        _routes[token] = file
        port = _server.server_address[1]
    return f"http://127.0.0.1:{port}{token}"


def open_preview(path: str | Path) -> str:
    url = preview_url(path)
    if not webbrowser.open(url):
        raise RuntimeError(f"The default browser could not be opened. Open this local URL while EthicalArmor is running: {url}")
    return url
