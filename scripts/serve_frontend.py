"""Serve one prefixed static frontend for local Playwright checks."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    route_prefix = f"/{args.prefix}/"

    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            route = urlsplit(path).path
            relative = route[len(route_prefix) :] if route.startswith(route_prefix) else ""
            return str(directory / (relative or "index.html"))

        def log_message(self, format: str, *values: object) -> None:
            return

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
