from __future__ import annotations

from conftest import FakeModel, decision, make_runtime


def test_grounded_answer_emits_only_used_citations(evidence):
    second = type(evidence)(
        "S2",
        "returns",
        "chk_2",
        "Returns",
        ["Window"],
        "Returns vary by item.",
        "kb://returns",
        "2026-09-01T00:00:00Z",
        0.8,
    )
    model = FakeModel(decision("rag_answer"), "Delivery takes three to five business days. [S1]")
    runtime = make_runtime(model, [evidence, second])
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], "How long is delivery?", "127.0.0.1")
    assert [event.data["citation_id"] for event in events if event.event == "citation"] == ["S1"]
    assert events[-1].data["outcome"] == "rag_answer"


def test_unknown_citation_abstains(evidence):
    model = FakeModel(decision("rag_answer"), "Delivery is tomorrow. [S99]")
    runtime = make_runtime(model, [evidence])
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], "When is delivery?", "127.0.0.1")
    assert events[-1].data["outcome"] == "citation_validation_failed"
    assert not [event for event in events if event.event == "citation"]


def test_insufficient_evidence_never_calls_answer_model():
    model = FakeModel(decision("rag_answer"))
    runtime = make_runtime(model, [], "insufficient_evidence")
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], "Is this discontinued?", "127.0.0.1")
    assert events[-1].data["outcome"] == "insufficient_evidence"
    assert model.answer_calls == 0


def test_invalid_decision_fails_safe_to_clarification():
    model = FakeModel({"expected_action": "complaint_tool"})
    runtime = make_runtime(model)
    conversation = runtime.create_conversation()
    events = runtime.send_message(conversation["id"], "Something happened", "127.0.0.1")
    assert events[-1].data["outcome"] == "clarify"


def test_history_sent_to_model_is_bounded_to_eight_turns():
    model = FakeModel(decision())
    runtime = make_runtime(model)
    conversation = runtime.create_conversation()
    for number in range(12):
        runtime.repository.add_message(conversation["id"], "user", f"old {number}", None)
    runtime.send_message(conversation["id"], "current", "127.0.0.1")
    assert model.decide_calls == 1
    assert runtime.repository.conversation(conversation["id"])["summary"]
