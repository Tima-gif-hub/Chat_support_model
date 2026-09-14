from __future__ import annotations

import os
import pathlib
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME_URL = os.getenv("RUNTIME_URL", "http://runtime-api:8000")
CUSTOMER_URL = os.getenv("CUSTOMER_URL", "http://customer-chat:3000")
MANAGER_URL = os.getenv("MANAGER_URL", "http://manager-console:3000")


class Gateway(BaseHTTPRequestHandler):
    server_version = "AFC-Gateway/1.0"

    def _send_file(self, path: pathlib.Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }
        content_type = content_types.get(path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, upstream: str | None = None, timeout: float = 30.0) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        target = upstream or RUNTIME_URL
        url = f"{target.rstrip('/')}{self.path}"
        # Forward cookies and the request's content negotiation headers.  The
        # gateway is intentionally a same-origin hop; it must not manufacture
        # an auth header or expose the private service URLs to the browser.
        forward_headers = {
            "Accept": self.headers.get("Accept", "*/*"),
            "Content-Type": self.headers.get("Content-Type", "application/json"),
        }
        if self.headers.get("Cookie"):
            forward_headers["Cookie"] = self.headers["Cookie"]
        if self.headers.get("Last-Event-ID"):
            forward_headers["Last-Event-ID"] = self.headers["Last-Event-ID"]
        # Ignore a client-supplied forwarding header; this hop is the trust
        # boundary for the IP-based rate limiter.
        forward_headers["X-Forwarded-For"] = self.client_address[0]
        request = urllib.request.Request(
            url, data=body, method=self.command, headers=forward_headers
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {
                        "connection",
                        "transfer-encoding",
                        "server",
                        "date",
                    }:
                        self.send_header(key, value)
                self._security_headers()
                self.end_headers()
                if "text/event-stream" in response.headers.get("Content-Type", ""):
                    # Do not buffer the runtime stream at the same-origin hop:
                    # each event must reach the browser as soon as it is
                    # available for status/token rendering and replay.
                    while True:
                        chunk = response.read(4096)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                else:
                    self.wfile.write(response.read())
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() not in {"connection", "transfer-encoding", "server", "date"}:
                    self.send_header(key, value)
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_error(503, "runtime unavailable")

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")

    def _frontend(self, upstream: str) -> None:
        # Frontend nginx instances own their static roots and SPA fallback.  A
        # file lookup in this container made /customer/styles.css and
        # /manager/app.mjs 404 in the assembled stack, so route the complete
        # path (including its query string) to the actual frontend service.
        self._proxy(upstream, timeout=10.0)

    def do_GET(self) -> None:  # noqa: N802
        if (
            self.path.startswith("/api/")
            or self.path.startswith("/health/")
            or urlsplit(self.path).path == "/version"
        ):
            self._proxy()
            return
        path = urlsplit(self.path).path
        if path in {"/", ""}:
            self.send_response(302)
            self.send_header("Location", "/customer/")
            self._security_headers()
            self.end_headers()
            return
        if path == "/customer" or path.startswith("/customer/"):
            if path == "/customer":
                self.send_response(308)
                self.send_header("Location", "/customer/")
                self._security_headers()
                self.end_headers()
                return
            self._frontend(CUSTOMER_URL)
            return
        if path == "/manager" or path.startswith("/manager/"):
            if path == "/manager":
                self.send_response(308)
                self.send_header("Location", "/manager/")
                self._security_headers()
                self.end_headers()
                return
            self._frontend(MANAGER_URL)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        self._proxy(RUNTIME_URL, timeout=35.0)

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy(RUNTIME_URL, timeout=10.0)

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy(RUNTIME_URL, timeout=10.0)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Allow", "GET,POST,PATCH,DELETE,OPTIONS")
        self._security_headers()
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"gateway {self.address_string()} {fmt % args}")


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    ThreadingHTTPServer((host, port), Gateway).serve_forever()


if __name__ == "__main__":
    main()
