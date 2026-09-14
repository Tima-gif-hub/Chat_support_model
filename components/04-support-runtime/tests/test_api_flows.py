from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from support_runtime.api import create_app
from support_runtime.config import RuntimeConfig
from support_runtime.postgres import PostgresRepository
from support_runtime.providers import StaticRetrievalProvider
from support_runtime.service import SupportRuntime
from support_runtime.storage import SQLiteRepository


class AnswerModel:
    model_version = "api-test-model"

    def decide(self, message: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "class": "general_faq",
            "intent": "general_help",
            "expected_action": "answer",
            "rag_required": False,
            "safety_class": "normal",
            "clarification_question": None,
            "complaint": None,
        }

    def answer(self, *args: Any) -> str:
        return "A safe answer."


def client(runtime: SupportRuntime | None = None) -> Any:
    test_client = pytest.importorskip("fastapi.testclient").TestClient
    runtime = runtime or SupportRuntime(
        SQLiteRepository(), AnswerModel(), StaticRetrievalProvider(), RuntimeConfig()
    )
    return test_client(create_app(runtime))


def test_customer_session_mints_cookie_and_scopes_conversation() -> None:
    first = client()
    created = first.post("/api/v1/conversations", json={"customer_id": "untrusted"})
    assert created.status_code == 201
    payload = created.json()
    assert "id" not in payload
    assert "support_customer_session" in first.cookies
    conversation_id = payload["conversation_id"]
    assert first.get(f"/api/v1/conversations/{conversation_id}").status_code == 200

    other = client()
    other.post("/api/v1/conversations", json={})
    assert other.get(f"/api/v1/conversations/{conversation_id}").status_code == 404


def test_sse_uses_runtime_event_envelope() -> None:
    browser = client()
    conversation_id = browser.post("/api/v1/conversations", json={}).json()["conversation_id"]
    response = browser.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"message": "Hello there"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"request_id":"req_' in response.text
    assert '"data":{"text":"A safe answer."}' in response.text


def test_postgres_history_is_json_safe_for_multi_turn_provider_requests() -> None:
    """psycopg timestamptz values must not leak into model request JSON."""

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def execute(self, *_: Any) -> None:
            return None

        def fetchall(self) -> list[dict[str, Any]]:
            return [{"role": "user", "content": "hello", "created_at": datetime.now(UTC)}]

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    repository = PostgresRepository.__new__(PostgresRepository)
    repository.connection = Connection()
    history = repository.messages("cnv_test")
    assert isinstance(history[0]["created_at"], str)


def test_manager_session_and_storage_field_mapping() -> None:
    runtime = SupportRuntime(
        SQLiteRepository(), AnswerModel(), StaticRetrievalProvider(), RuntimeConfig()
    )
    conversation = runtime.create_conversation("customer-for-manager-test")
    complaint = runtime.repository.submit_complaint(
        runtime.config.workspace_id,
        conversation["id"],
        conversation["customer_id"],
        {
            "complaint_text": "The delivery is five days late and needs manager help.",
            "complaint_type": "delivery_delay",
            "customer_context": "Synthetic test context",
        },
        "confirmed",
    )
    browser = client(runtime)
    unauthorized = browser.get("/api/v1/manager/complaints")
    assert unauthorized.status_code == 403
    assert unauthorized.json()["error"]["code"] == "forbidden"
    login = browser.post(
        "/api/v1/manager/session",
        json={"email": "manager@example.test", "password": "portfolio-manager"},
    )
    assert login.status_code == 200
    records = browser.get("/api/v1/manager/complaints").json()
    assert records[0]["complaint_id"] == complaint["complaint_id"]
    assert records[0]["complaint_text"].startswith("The delivery")
    assert records[0]["internal_notes"] == ""
    updated = browser.patch(
        f"/api/v1/manager/complaints/{complaint['complaint_id']}",
        json={"version": 1, "internal_notes": "Review delivery timeline."},
    )
    assert updated.status_code == 200
    assert updated.json()["internal_notes"] == "Review delivery timeline."


def test_invalid_request_has_correct_json_response_shape() -> None:
    browser = client()
    browser.post("/api/v1/conversations", json={})
    response = browser.post("/api/v1/conversations/nope/messages", json={"message": "hello"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_empty_event_replay_is_a_successful_empty_stream() -> None:
    browser = client()
    conversation_id = browser.post("/api/v1/conversations", json={}).json()["conversation_id"]
    response = browser.get(f"/api/v1/conversations/{conversation_id}/events")
    assert response.status_code == 200
    assert response.text == ""
    assert "x-request-id" not in response.headers


def test_json_write_endpoints_reject_missing_content_type() -> None:
    runtime = SupportRuntime(
        SQLiteRepository(), AnswerModel(), StaticRetrievalProvider(), RuntimeConfig()
    )
    conversation = runtime.create_conversation("customer-for-mime-test")
    complaint = runtime.repository.submit_complaint(
        runtime.config.workspace_id,
        conversation["id"],
        conversation["customer_id"],
        {
            "complaint_text": "The delivery is late and needs manager help.",
            "complaint_type": "delivery_delay",
            "customer_context": "Synthetic test context",
        },
        "confirmed",
    )
    browser = client(runtime)
    owned_id = browser.post("/api/v1/conversations", json={}).json()["conversation_id"]
    sent = browser.post(
        f"/api/v1/conversations/{owned_id}/messages", json={"message": "Hello there"}
    )
    assert sent.status_code == 200
    assistant_id = next(
        item["id"] for item in runtime.repository.messages(owned_id) if item["role"] == "assistant"
    )
    feedback = browser.post(
        f"/api/v1/messages/{assistant_id}/feedback",
        content='{"rating":1}',
    )
    assert feedback.status_code == 400
    assert feedback.json()["error"]["code"] == "invalid_request"
    login = browser.post(
        "/api/v1/manager/session",
        json={"email": "manager@example.test", "password": "portfolio-manager"},
    )
    assert login.status_code == 200
    patch = browser.patch(
        f"/api/v1/manager/complaints/{complaint['complaint_id']}",
        content='{"version":1}',
    )
    assert patch.status_code == 400
    assert patch.json()["error"]["code"] == "invalid_request"


def test_bearer_role_cannot_be_selected_by_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANAGER_API_TOKEN", "test-token")
    monkeypatch.setenv("MANAGER_API_ROLE", "manager")
    browser = client()
    response = browser.get(
        "/api/v1/manager/complaints",
        headers={"Authorization": "Bearer test-token", "X-Manager-Role": "admin"},
    )
    assert response.status_code == 200


def test_production_rejects_demo_security_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        client()
