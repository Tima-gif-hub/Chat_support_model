from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .service import RagPlatform


def create_app(source_directory: Path | None = None):
    try:
        from fastapi import FastAPI, Header, HTTPException
    except ImportError as exc:  # pragma: no cover - exercised by the container profile
        raise RuntimeError("Install the server dependency group to run the HTTP API") from exc

    source_directory = source_directory or Path(
        os.getenv("RAG_SOURCE_DIR", "/app/fixtures/knowledge-base")
    )
    index_version = os.getenv("RAG_INDEX_VERSION", "idx_local_fixture_v1")
    database_url = os.getenv("RAG_DATABASE_URL")
    service = (
        RagPlatform.from_postgres(database_url, index_version)
        if database_url
        else RagPlatform.from_fixtures(source_directory, index_version)
    )
    app = FastAPI(title="RAG platform", version="1.0.0")

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        body = {
            "status": "ready",
            "index_version": service.index_version,
            "backend": service.backend,
        }
        if not service.ready():
            raise HTTPException(status_code=503, detail={**body, "status": "not_ready"})
        return body

    @app.get("/version")
    def version() -> dict[str, str]:
        return {
            "service": "rag-platform",
            "git_sha": os.getenv("GIT_SHA", "local"),
            "contract_version": "1.0.0",
            "index_version": service.index_version,
            "backend": service.backend,
        }

    @app.get("/metrics")
    def metrics() -> str:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            service.metrics.prometheus(), media_type="text/plain; version=0.0.4"
        )

    @app.post("/v1/retrieve")
    def retrieve(
        request: dict[str, object],
        x_workspace_id: str = Header(...),
        x_audience: str = Header(...),
        x_language: str = Header(...),
    ) -> dict[str, object]:
        # These headers are set by the authenticated runtime on the private network. The public
        # gateway must not route directly to this service.
        if x_workspace_id != "anonymous-furniture-company" or x_audience != "customer":
            raise HTTPException(status_code=403, detail="retrieval context is not authorized")
        query = request.get("query")
        if not isinstance(query, str) or not 1 <= len(query) <= 2000:
            raise HTTPException(status_code=422, detail="query must contain 1 to 2000 characters")
        as_of_raw = request.get("as_of")
        try:
            as_of = (
                datetime.fromisoformat(str(as_of_raw).replace("Z", "+00:00"))
                if as_of_raw
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="as_of must be RFC3339") from exc
        if as_of is not None and as_of.tzinfo is None:
            raise HTTPException(status_code=422, detail="as_of must include timezone")
        try:
            return service.retrieve(
                query,
                workspace_id=x_workspace_id,
                audience=x_audience,
                language=x_language,
                as_of=as_of,
            ).as_dict()
        except Exception as exc:
            # A database/vector service failure is dependency unavailability,
            # distinct from a successful low-evidence response.
            raise HTTPException(
                status_code=503, detail="retrieval temporarily unavailable"
            ) from exc

    return app


app = create_app()
