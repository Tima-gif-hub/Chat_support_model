from __future__ import annotations

import json
import os
import urllib.request


def post(url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def get(url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{url}{path}", timeout=10) as response:
        return json.loads(response.read())


def main() -> int:
    rag = os.getenv("RAG_URL", "http://localhost:8002")
    runtime = os.getenv("RUNTIME_URL", "http://localhost:8000")
    try:
        rag_status = get(rag, "/health/ready")
        if rag_status.get("backend") != "postgres_pgvector":
            raise RuntimeError("RAG did not start with the PostgreSQL/pgvector backend")
        print(rag, rag_status)
        print(runtime, post(runtime, "/api/v1/seed", {}))
    except Exception as exc:
        raise SystemExit(f"seed verification failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
