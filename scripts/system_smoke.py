"""Assembled system smoke for the four cross-component journeys.

HTTP is the default whenever service URLs are provided. In-process execution is an explicit
developer/test mode only; CI and Compose never silently downgrade to it.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _opener() -> urllib.request.OpenerDirector:
    # Keep one cookie jar for the entire smoke journey.  The runtime mints an
    # anonymous customer cookie on conversation creation and a signed manager
    # cookie on login; rebuilding the opener between calls would turn both
    # authentication checks into false positives.
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.cookie_jar = jar  # type: ignore[attr-defined]
    return opener


def request(
    client: urllib.request.OpenerDirector,
    base: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}", data=data, method=method, headers=request_headers
    )
    try:
        with client.open(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                events: list[dict[str, Any]] = []
                for block in raw.split("\n\n"):
                    data_lines = [
                        line[6:] for line in block.splitlines() if line.startswith("data: ")
                    ]
                    if data_lines:
                        event = json.loads("".join(data_lines))
                        if not isinstance(event, dict):
                            raise AssertionError("SSE event data must be an object")
                        events.append(event)
                return response.status, events
            if not raw:
                return response.status, None
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail: Any = json.loads(body)
        except json.JSONDecodeError:
            detail = body
        raise AssertionError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc


def assert_public_frontend(client: urllib.request.OpenerDirector, base: str) -> None:
    """Prove the gateway serves both HTML shells and executable module assets."""
    checks = (
        ("/customer/?smoke=1", "text/html", "Public portfolio interface"),
        ("/customer/app.mjs", "javascript", "const API"),
        ("/manager/?smoke=1", "text/html", "Manager console"),
        ("/manager/app.mjs", "javascript", "const API"),
    )
    for path, expected_type, marker in checks:
        req = urllib.request.Request(f"{base.rstrip('/')}{path}", method="GET")
        try:
            with client.open(req, timeout=10) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                body = response.read().decode("utf-8", errors="replace")
                invalid_response = (
                    response.status != 200
                    or expected_type not in content_type
                    or marker not in body
                )
                if invalid_response:
                    raise AssertionError(f"public asset route returned an invalid response: {path}")
        except urllib.error.HTTPError as exc:
            raise AssertionError(f"GET {path} returned HTTP {exc.code}") from exc


def assert_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list) or not events:
        raise AssertionError("runtime response must contain at least one SSE event")
    # Import only the generated, dependency-free wire validator.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "packages/python-contracts"))
    from support_contracts import validate_runtime_event

    previous = 0
    for event in events:
        validate_runtime_event(event)
        if event["sequence"] <= previous:
            raise AssertionError("runtime event sequence must increase monotonically")
        previous = event["sequence"]
    return events


def wait_ready(client: urllib.request.OpenerDirector, base: str) -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            status, body = request(client, base, "GET", "/health/ready")
            if status == 200 and isinstance(body, dict):
                return
        except (OSError, AssertionError):
            pass
        time.sleep(0.25)
    raise SystemExit(f"service not ready: {base}")


def http_smoke() -> int:
    runtime = os.getenv("RUNTIME_URL")
    rag = os.getenv("RAG_URL", "http://localhost:8002")
    model = os.getenv("MODEL_URL", "http://localhost:8001")
    public = os.getenv("PUBLIC_URL")
    if not runtime:
        raise SystemExit(
            "RUNTIME_URL is required for HTTP smoke; set "
            "SMOKE_IN_PROCESS=1 explicitly for local unit mode"
        )
    client = _opener()
    versions: dict[str, dict[str, Any]] = {}
    for name, base in (("runtime", runtime), ("rag", rag), ("model", model)):
        wait_ready(client, base)
        status, version = request(client, base, "GET", "/version")
        if status != 200 or not isinstance(version, dict) or not version.get("contract_version"):
            raise AssertionError(f"{base} returned an invalid version identity")
        versions[name] = version
    if public:
        wait_ready(client, public)
        assert_public_frontend(client, public)
    if versions["runtime"].get("model_version") != versions["model"].get("model_version"):
        raise AssertionError("runtime and model-serving versions disagree")
    if versions["runtime"].get("index_version") != versions["rag"].get("index_version"):
        raise AssertionError("runtime and RAG index versions disagree")

    _, conversation = request(client, runtime, "POST", "/api/v1/conversations", {})
    if not isinstance(conversation, dict) or not conversation.get("conversation_id"):
        raise AssertionError("conversation creation did not return conversation_id")
    jar = getattr(client, "cookie_jar", None)
    if jar is None or not any(cookie.name == "support_customer_session" for cookie in jar):
        raise AssertionError("conversation creation did not persist the customer session cookie")
    cid = str(conversation["conversation_id"])
    status, owned = request(client, runtime, "GET", f"/api/v1/conversations/{cid}")
    if status != 200 or not isinstance(owned, dict) or owned.get("conversation_id") != cid:
        raise AssertionError("persisted customer session was not accepted for conversation access")

    _, grounded_raw = request(
        client,
        runtime,
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        {"message": "What are the delivery costs?"},
    )
    grounded = assert_events(grounded_raw)
    if not any(event["event"] == "citation" for event in grounded):
        raise AssertionError("grounded response must cite RAG evidence")

    _, abstain_raw = request(
        client,
        runtime,
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        {"message": "Can delivery reach a quasar depot?"},
    )
    abstain = assert_events(abstain_raw)
    if not any(
        event["event"] == "completed" and event["data"].get("outcome") == "insufficient_evidence"
        for event in abstain
    ):
        raise AssertionError("insufficient evidence journey did not abstain")

    _, draft_raw = request(
        client,
        runtime,
        "POST",
        f"/api/v1/conversations/{cid}/messages",
        {"message": "My delivery is five days late and this is frustrating."},
    )
    draft_events = assert_events(draft_raw)
    draft_event = next(
        event for event in draft_events if event["event"] == "complaint.confirmation_required"
    )
    draft_id = str(draft_event["data"]["draft_id"])
    _, submitted = request(
        client, runtime, "POST", f"/api/v1/conversations/{cid}/complaints/{draft_id}/confirm", {}
    )
    if not isinstance(submitted, dict) or submitted.get("status") != "queued":
        raise AssertionError("confirmed complaint was not queued")
    _, duplicate = request(
        client, runtime, "POST", f"/api/v1/conversations/{cid}/complaints/{draft_id}/confirm", {}
    )
    if (
        not isinstance(duplicate, dict)
        or duplicate.get("complaint_id") != submitted.get("complaint_id")
        or duplicate.get("duplicate") is not True
    ):
        raise AssertionError("complaint confirmation is not idempotent")

    # Cross the runtime -> manager boundary and verify the persisted queue item.
    _, login = request(
        client,
        runtime,
        "POST",
        "/api/v1/manager/session",
        {
            "email": os.getenv("MANAGER_EMAIL", "manager@example.test"),
            "password": os.getenv("MANAGER_PASSWORD", "portfolio-manager"),
        },
    )
    if not isinstance(login, dict) or login.get("authenticated") is not True:
        raise AssertionError("manager session was not created")
    if jar is None or not any(cookie.name == "support_manager_session" for cookie in jar):
        raise AssertionError("manager login did not persist the signed manager session cookie")
    status, session = request(client, runtime, "GET", "/api/v1/manager/session")
    if status != 200 or not isinstance(session, dict) or session.get("authenticated") is not True:
        raise AssertionError("persisted manager session was not accepted by the session endpoint")
    # Deliberately omit the role header here: this request proves the cookie
    # session is sufficient and is not accidentally relying on a caller-owned
    # authorization hint.
    _, queue = request(client, runtime, "GET", "/api/v1/manager/complaints")
    if not isinstance(queue, list) or not any(
        item.get("complaint_id") == submitted.get("complaint_id")
        for item in queue
        if isinstance(item, dict)
    ):
        raise AssertionError("queued complaint is not visible in manager queue")
    print(
        "system smoke passed: service identities, RAG citations, abstention, "
        "complaint consent, manager queue, idempotency"
    )
    return 0


def in_process_smoke() -> int:
    """Explicit dependency-free cross-component smoke for local test environments."""
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [
        str(root / "packages/python-contracts"),
        str(root / "components/02-model-serving/src"),
        str(root / "components/03-rag-platform/src"),
        str(root / "components/04-support-runtime/src"),
    ]
    from model_serving.contracts import ChatRequest
    from model_serving.providers import DeterministicMockProvider
    from rag_platform import RagPlatform
    from support_runtime.config import RuntimeConfig
    from support_runtime.domain import Evidence, RetrievalResult
    from support_runtime.service import SupportRuntime
    from support_runtime.storage import SQLiteRepository

    model_provider = DeterministicMockProvider()
    model_provider.load()
    rag = RagPlatform.from_fixtures(root / "components/03-rag-platform/fixtures/knowledge-base")

    class LocalModel:
        model_version = "mock-1.0.0"

        def decide(self, message, history):
            raw = model_provider.complete(
                ChatRequest(({"role": "user", "content": message},), 1024, 42)
            )
            return json.loads(raw)

        def answer(self, message, evidence, summary, history):
            reference = "\n".join(
                f"<{item.citation_id}>\n{item.content}\n</{item.citation_id}>" for item in evidence
            )
            raw = model_provider.complete(
                ChatRequest(
                    (
                        {
                            "role": "system",
                            "content": (
                                "Cite every company-factual sentence with allowed [S#] IDs.\n"
                            )
                            + reference,
                        },
                        {"role": "user", "content": message},
                    ),
                    1024,
                    None,
                )
            )
            return raw

    class LocalRag:
        index_version = rag.index_version

        def retrieve(self, query, workspace_id, language="en"):
            result = rag.retrieve(
                query, workspace_id=workspace_id, audience="customer", language=language
            )
            evidence = [
                Evidence(
                    item.citation_id,
                    item.document_id,
                    item.chunk_id,
                    item.title,
                    list(item.heading_path),
                    item.content,
                    item.source_uri,
                    item.updated_at.isoformat().replace("+00:00", "Z"),
                    item.reranker_score,
                )
                for item in result.evidence
            ]
            return RetrievalResult(result.query_id, result.index_version, result.status, evidence)

    runtime = SupportRuntime(
        SQLiteRepository(":memory:"), LocalModel(), LocalRag(), RuntimeConfig()
    )
    conversation = runtime.create_conversation()
    grounded = runtime.send_message(conversation["id"], "What are the delivery costs?", "127.0.0.1")
    if not any(event.event == "citation" for event in grounded):
        raise AssertionError("in-process grounded journey lacks citation")
    abstain = runtime.send_message(
        conversation["id"], "Can delivery reach a quasar depot?", "127.0.0.1"
    )
    if not any(
        event.event == "completed" and event.data.get("outcome") == "insufficient_evidence"
        for event in abstain
    ):
        raise AssertionError("in-process abstention journey failed")
    draft = runtime.send_message(
        conversation["id"], "My delivery is five days late and this is frustrating.", "127.0.0.1"
    )
    confirmation = next(
        event for event in draft if event.event == "complaint.confirmation_required"
    )
    submitted = runtime.confirm_complaint(conversation["id"], confirmation.data["draft_id"])
    duplicate = runtime.confirm_complaint(conversation["id"], confirmation.data["draft_id"])
    if (
        submitted["status"] != "queued"
        or not duplicate.get("duplicate")
        or not any(
            item["id"] == submitted["complaint_id"] for item in runtime.repository.list_complaints()
        )
    ):
        raise AssertionError("in-process complaint queue/idempotency journey failed")
    print(
        "system smoke passed in-process: RAG -> runtime citations, abstention, "
        "complaint persistence, manager queue, idempotency"
    )
    return 0


def main() -> int:
    if os.getenv("SMOKE_IN_PROCESS") == "1":
        return in_process_smoke()
    try:
        return http_smoke()
    except Exception:
        # Fallback must be opt-in and is forbidden in CI/Compose where it would hide a broken stack.
        if (
            os.getenv("SMOKE_FALLBACK") == "1"
            and not os.getenv("CI")
            and not os.getenv("COMPOSE_PROJECT_NAME")
        ):
            return in_process_smoke()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
