#!/usr/bin/env python3
"""Development server for the checkout app.

Serves the static files in ``public/`` and a tiny JSON API:

* ``POST /api/orders`` -> 201 ``{"order_id": "ORD-<n>"}``
* ``GET /healthz``     -> 200 ``{"status": "ok"}``

Run it with ``python3 serve.py --port 8000`` or import ``make_server`` to start
it on a free port from tests.
"""

from __future__ import annotations

import argparse
import itertools
import json
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
REQUIRED_FIELDS = ("contact", "shipping", "items")
MAX_BODY_BYTES = 64 * 1024

_order_numbers = itertools.count(1001)
_order_lock = threading.Lock()


def next_order_id() -> str:
    with _order_lock:
        return f"ORD-{next(_order_numbers)}"


class CheckoutHandler(SimpleHTTPRequestHandler):
    server_version = "CheckoutDev/1.0"
    quiet = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        if not self.quiet:
            super().log_message(format, *args)

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/healthz":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/orders":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid Content-Length"})
            return

        raw = self.rfile.read(length)
        try:
            order = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "request body must be valid JSON"})
            return

        if not isinstance(order, dict):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "request body must be a JSON object"})
            return

        missing = [field for field in REQUIRED_FIELDS if not order.get(field)]
        if missing:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "missing required fields", "fields": missing},
            )
            return

        self.send_json(HTTPStatus.CREATED, {"order_id": next_order_id()})


def make_server(port: int = 0, host: str = "127.0.0.1") -> tuple[ThreadingHTTPServer, str]:
    """Create (but do not start) the server. Returns ``(server, base_url)``."""
    server = ThreadingHTTPServer((host, port), CheckoutHandler)
    bound_host, bound_port = server.server_address[:2]
    return server, f"http://{bound_host}:{bound_port}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the checkout app and order API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args()

    CheckoutHandler.quiet = not args.verbose
    server, base_url = make_server(args.port, args.host)
    print(f"Checkout app running at {base_url}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
