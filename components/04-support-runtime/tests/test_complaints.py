from __future__ import annotations

from conftest import FakeModel, decision, make_runtime


def complaint(mode: str, evidence: str | None) -> dict:
    return {
        "complaint_text": "The delivery is five days late and I need assistance.",
        "category": "complaint",
        "complaint_type": "delivery_delay",
        "customer_context": "Order details were not provided.",
        "submission_mode": mode,
        "consent_evidence": evidence,
    }


def test_inferred_complaint_requires_confirmation():
    model = FakeModel(
        decision("complaint_tool", complaint=complaint("confirmation_required", None))
    )
    runtime = make_runtime(model)
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], "My delivery is five days late", "127.0.0.1")
    required = next(event for event in events if event.event == "complaint.confirmation_required")
    assert runtime.repository.list_complaints() == []
    result = runtime.confirm_complaint(conversation["id"], required.data["draft_id"])
    assert result["status"] == "queued"
    assert len(runtime.repository.audit_events(result["complaint_id"])) == 1


def test_explicit_current_message_consent_submits_once():
    phrase = "Please send this complaint to a manager"
    model = FakeModel(decision("complaint_tool", complaint=complaint("explicit_request", phrase)))
    runtime = make_runtime(model)
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], phrase, "127.0.0.1")
    submitted = next(event for event in events if event.event == "complaint.submitted")
    assert submitted.data["duplicate"] is False
    duplicate = runtime.repository.submit_complaint(
        runtime.config.workspace_id,
        conversation["id"],
        None,
        runtime._tool_payload(complaint("explicit_request", phrase)),
        "explicit_request",
    )
    assert duplicate["duplicate"] is True
    assert len(runtime.repository.list_complaints()) == 1
    assert [
        x["event_type"] for x in runtime.repository.audit_events(duplicate["complaint_id"])
    ] == ["complaint.created", "complaint.duplicate"]


def test_fabricated_consent_evidence_creates_draft():
    model = FakeModel(
        decision("complaint_tool", complaint=complaint("explicit_request", "send this"))
    )
    runtime = make_runtime(model)
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], "The delivery is late", "127.0.0.1")
    assert any(event.event == "complaint.confirmation_required" for event in events)
    assert runtime.repository.list_complaints() == []


def test_manager_update_uses_optimistic_version():
    phrase = "Please send this complaint to a manager"
    model = FakeModel(decision("complaint_tool", complaint=complaint("explicit_request", phrase)))
    runtime = make_runtime(model)
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], phrase, "127.0.0.1")
    complaint_id = next(e.data["complaint_id"] for e in events if e.event == "complaint.submitted")
    updated = runtime.repository.update_complaint(
        complaint_id, 1, "acknowledged", "Reviewing", "mgr"
    )
    assert updated["version"] == 2
