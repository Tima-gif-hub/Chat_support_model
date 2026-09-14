import json
import os
from collections.abc import Iterator
from typing import Any

from .config import RuntimeConfig
from .errors import RuntimeErrorBase, ValidationError
from .guardrails import RedisRateLimiter
from .postgres import PostgresRepository
from .providers import HTTPModelProvider, HTTPRetrievalProvider
from .service import SupportRuntime
from .sessions import (
    CUSTOMER_COOKIE,
    MANAGER_COOKIE,
    cookie_options,
    customer_from_cookie,
    manager_from_cookie,
    new_customer_session,
    new_manager_session,
    validate_security_configuration,
)
from .storage import SQLiteRepository


def _public_conversation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: value for key, value in item.items() if key != "id"},
        "conversation_id": item["id"],
    }


def _manager_complaint_payload(service: SupportRuntime, item: dict[str, Any]) -> dict[str, Any]:
    """Map storage names to the stable manager-console response contract."""
    complaint_id = str(item.get("id", item.get("complaint_id", "")))
    audit = []
    for event in service.repository.audit_events(complaint_id):
        event_type = str(event.get("event_type", "audit"))
        payload = event.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if event_type == "complaint.status_changed" and isinstance(payload, dict):
            text = f"Status changed to {payload.get('status', 'updated')}."
        elif event_type == "complaint.duplicate":
            text = "Duplicate submission detected; existing complaint retained."
        elif event_type == "complaint.created":
            text = "Complaint queued after customer consent."
        else:
            text = event_type.replace(".", " ").capitalize()
        created_at = event.get("created_at", "")
        audit.append({"at": str(created_at), "text": text})
    return {
        "complaint_id": complaint_id,
        "workspace_id": item.get("workspace_id", service.config.workspace_id),
        "conversation_id": item.get("conversation_id"),
        "customer_id": item.get("customer_id"),
        "complaint_text": item.get("complaint_text", ""),
        "complaint_type": item.get("complaint_type", "other"),
        "category": item.get("category", "complaint"),
        "status": item.get("status", "queued"),
        "duplicate": False,
        "consent_source": item.get("consent_source", "confirmed"),
        "customer_context": item.get("customer_context", ""),
        "internal_notes": item.get("internal_notes", ""),
        "version": int(item.get("version", 1)),
        "created_at": str(item.get("created_at", "")),
        "updated_at": str(item.get("updated_at", "")),
        "audit": audit,
    }


def _sse(events: list[dict[str, Any]]) -> Iterator[str]:
    for event in events:
        # Keep the complete runtime event in the SSE data envelope.  Clients
        # can render ``data`` while request_id/sequence remain available for
        # replay and tracing.
        yield (
            f"id: {event['sequence']}\n"
            f"event: {event['event']}\n"
            f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
        )


def build_runtime() -> SupportRuntime:
    config = RuntimeConfig.load(os.getenv("RUNTIME_CONFIG"))
    database_url = os.getenv("DATABASE_URL")
    repository = (
        PostgresRepository(database_url)
        if database_url
        else SQLiteRepository(os.getenv("RUNTIME_SQLITE_PATH", ":memory:"))
    )
    model = HTTPModelProvider(
        os.getenv("MODEL_BASE_URL", "http://model-mock:8000"),
        os.getenv("MODEL_VERSION", "deterministic-simulator"),
        config.decision_timeout_seconds,
        config.answer_timeout_seconds,
    )
    retrieval = HTTPRetrievalProvider(
        os.getenv("RAG_BASE_URL", "http://rag-api:8000"),
        config.rag_timeout_seconds,
        os.getenv("INDEX_VERSION", "unknown"),
    )
    limiter = None
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        limiter = RedisRateLimiter(redis_url)
    return SupportRuntime(repository, model, retrieval, config, limiter=limiter)


def create_app(runtime: SupportRuntime | None = None) -> Any:
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
        from fastapi.exceptions import RequestValidationError
        from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
    except ImportError as exc:  # pragma: no cover - deployment dependency check
        raise RuntimeError("install the 'server' dependencies to run the HTTP API") from exc

    validate_security_configuration()
    service = runtime or build_runtime()
    app = FastAPI(title="Support runtime", version=service.config.contract_version)

    @app.exception_handler(RuntimeErrorBase)
    async def runtime_error_handler(request: Request, exc: RuntimeErrorBase) -> JSONResponse:
        return JSONResponse(
            content={"error": {"code": exc.code, "message": str(exc)}},
            status_code=exc.status_code,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "invalid_request",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            content={"error": {"code": code, "message": str(exc.detail)}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "request parameters are invalid",
                }
            },
            status_code=422,
        )

    def customer_auth(request: Request) -> str:
        customer_id = customer_from_cookie(request.cookies.get(CUSTOMER_COOKIE))
        if not customer_id:
            raise HTTPException(
                status_code=401,
                detail="customer session required",
                headers={"WWW-Authenticate": "Session"},
            )
        return customer_id

    def manager_auth(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> str:
        expected = os.getenv("MANAGER_API_TOKEN")
        if expected and authorization == f"Bearer {expected}":
            role = os.getenv("MANAGER_API_ROLE", "manager")
            return role if role in {"manager", "admin"} else "manager"
        identity = manager_from_cookie(request.cookies.get(MANAGER_COOKIE))
        if identity is None:
            raise HTTPException(
                status_code=403,
                detail="manager session required",
            )
        return identity["role"]

    @app.post("/api/v1/manager/session")
    async def manager_login(request: Request, response: Response) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise ValidationError("Content-Type must be application/json")
        try:
            body = await request.json()
        except (TypeError, ValueError) as exc:
            raise ValidationError("request body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ValidationError("request body must be an object")
        if set(body) - {"email", "password"}:
            raise ValidationError("unknown manager session fields")
        email = body.get("email")
        password = body.get("password")
        expected_email = os.getenv("MANAGER_EMAIL", "manager@example.test")
        expected_password = os.getenv("MANAGER_PASSWORD", "portfolio-manager")
        if email != expected_email or password != expected_password:
            raise HTTPException(status_code=401, detail="invalid manager credentials")
        role = os.getenv("MANAGER_ROLE", "manager")
        if role not in {"manager", "admin"}:
            role = "manager"
        response.set_cookie(
            MANAGER_COOKIE,
            new_manager_session(str(email), role),
            max_age=8 * 3600,
            **cookie_options(),
        )
        return {"authenticated": True, "email": str(email), "role": role}

    @app.get("/api/v1/manager/session")
    async def manager_session(request: Request) -> dict[str, Any]:
        identity = manager_from_cookie(request.cookies.get(MANAGER_COOKIE))
        if identity is None:
            raise HTTPException(status_code=401, detail="manager session required")
        return {"authenticated": True, **identity}

    @app.delete("/api/v1/manager/session", status_code=204, response_model=None)
    async def manager_logout(response: Response) -> Response:
        response.delete_cookie(MANAGER_COOKIE, path="/")
        response.status_code = 204
        return response

    @app.post("/api/v1/conversations", status_code=201)
    async def create_conversation(request: Request, response: Response) -> dict[str, Any]:
        customer_id = customer_from_cookie(request.cookies.get(CUSTOMER_COOKIE))
        if customer_id is None:
            customer_id, token = new_customer_session()
            response.set_cookie(CUSTOMER_COOKIE, token, max_age=24 * 3600, **cookie_options())
        body: Any = {}
        if request.headers.get("content-length", "0") != "0":
            try:
                body = await request.json()
            except (TypeError, ValueError) as exc:
                raise ValidationError("request body must be valid JSON") from exc
            if not isinstance(body, dict):
                raise ValidationError("request body must be an object")
            if set(body) - {"customer_id", "session_id"}:
                raise ValidationError("unknown conversation fields")
        # customer_id in the request is deliberately ignored: ownership comes
        # from the signed session minted above.
        conversation = service.create_conversation(customer_id)
        return _public_conversation(conversation)

    @app.get("/api/v1/conversations/{conversation_id}")
    async def get_conversation(
        conversation_id: str, customer_id: str = Depends(customer_auth)
    ) -> dict[str, Any]:
        conversation = service.get_conversation(conversation_id, customer_id)
        return _public_conversation(conversation)

    @app.post("/api/v1/conversations/{conversation_id}/messages")
    async def send_message(
        conversation_id: str,
        request: Request,
        customer_id: str = Depends(customer_auth),
    ) -> StreamingResponse:
        if "application/json" not in request.headers.get("content-type", ""):
            raise ValidationError("Content-Type must be application/json")
        try:
            body = await request.json()
        except (TypeError, ValueError) as exc:
            raise ValidationError("request body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ValidationError("request body must be an object")
        if set(body) != {"message"}:
            raise ValidationError("message request must contain only message")
        ip = request.client.host if request.client else "unknown"
        events = [
            event.as_dict()
            for event in service.send_message(
                conversation_id, body.get("message"), ip, customer_id=customer_id
            )
        ]
        return StreamingResponse(
            _sse(events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/conversations/{conversation_id}/events")
    async def replay_events(
        conversation_id: str,
        customer_id: str = Depends(customer_auth),
        last_event_id: int = 0,
        header_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        service.get_conversation(conversation_id, customer_id)
        try:
            cursor = int(header_event_id) if header_event_id is not None else last_event_id
        except ValueError as exc:
            raise ValidationError("Last-Event-ID must be an integer") from exc
        if cursor < 0:
            raise ValidationError("Last-Event-ID must not be negative")
        events = service.repository.events(conversation_id, cursor)
        headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        if events:
            headers["X-Request-ID"] = str(events[0]["request_id"])
        return StreamingResponse(
            _sse(events),
            media_type="text/event-stream",
            headers=headers,
        )

    @app.post("/api/v1/conversations/{conversation_id}/complaints/{draft_id}/confirm")
    async def confirm(
        conversation_id: str,
        draft_id: str,
        customer_id: str = Depends(customer_auth),
    ) -> dict[str, Any]:
        return service.confirm_complaint(conversation_id, draft_id, customer_id)

    @app.delete(
        "/api/v1/conversations/{conversation_id}/complaints/{draft_id}",
        status_code=204,
        response_model=None,
    )
    async def delete_draft(
        conversation_id: str,
        draft_id: str,
        customer_id: str = Depends(customer_auth),
    ) -> Response:
        service.delete_draft(conversation_id, draft_id, customer_id)
        return Response(status_code=204)

    @app.post("/api/v1/messages/{message_id}/feedback", status_code=201)
    async def feedback(
        message_id: str,
        request: Request,
        customer_id: str = Depends(customer_auth),
    ) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise ValidationError("Content-Type must be application/json")
        try:
            body = await request.json()
        except (TypeError, ValueError) as exc:
            raise ValidationError("request body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ValidationError("request body must be an object")
        if set(body) - {"rating", "comment"}:
            raise ValidationError("unknown feedback fields")
        return service.add_feedback(
            message_id, body.get("rating"), body.get("comment", ""), customer_id
        )

    @app.get("/api/v1/manager/complaints")
    async def complaints(
        status: str | None = None,
        limit: int = 100,
        _role: str = Depends(manager_auth),
    ) -> list[dict[str, Any]]:
        if status is not None and status not in {"queued", "acknowledged", "resolved", "failed"}:
            raise ValidationError("invalid complaint status filter")
        return [
            _manager_complaint_payload(service, item)
            for item in service.repository.list_complaints(status, min(max(limit, 1), 100))
        ]

    @app.patch("/api/v1/manager/complaints/{complaint_id}")
    async def update_complaint(
        complaint_id: str, request: Request, role: str = Depends(manager_auth)
    ) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise ValidationError("Content-Type must be application/json")
        try:
            body = await request.json()
        except (TypeError, ValueError) as exc:
            raise ValidationError("request body must be valid JSON") from exc
        try:
            if not isinstance(body, dict) or set(body) - {
                "version",
                "status",
                "internal_notes",
            }:
                raise TypeError
            current = service.repository.complaint(complaint_id)
            version = int(body["version"])
            status = body.get("status", current["status"])
            internal_notes = body.get("internal_notes", current["internal_notes"])
            if not isinstance(status, str) or not isinstance(internal_notes, str):
                raise TypeError
            updated = service.repository.update_complaint(
                complaint_id,
                version,
                status,
                internal_notes[:4000],
                role,
            )
            return _manager_complaint_payload(service, updated)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("invalid manager update") from exc

    @app.post("/api/v1/seed")
    async def seed() -> dict[str, str]:
        # Fixtures are immutable component-owned inputs and are loaded by the
        # providers at startup.  Keep the orchestrator endpoint idempotent so
        # the documented compose seed command can verify readiness.
        if not service.repository.ready():
            raise RuntimeErrorBase("runtime database is not ready")
        return {"status": "ready", "seed": "startup-fixtures"}

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        value = service.ready()
        return JSONResponse(content=value, status_code=200 if value["ready"] else 503)

    @app.get("/version")
    async def version() -> dict[str, str]:
        return service.version()

    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(
            service.metrics.prometheus(), media_type="text/plain; version=0.0.4"
        )

    return app


app = None
try:  # keeps package importable in dependency-light test environments
    app = create_app()
except (RuntimeError, OSError):
    pass
