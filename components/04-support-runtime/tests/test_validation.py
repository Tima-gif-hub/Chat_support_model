import pytest
from support_runtime.citations import validate_grounded_answer
from support_runtime.errors import ValidationError
from support_runtime.history import bounded_history
from support_runtime.validation import enforce_explicit_consent


def test_allowlist_requires_exact_current_message_substring():
    item = {"submission_mode": "explicit_request", "consent_evidence": "forward this complaint"}
    assert enforce_explicit_consent("Please forward this complaint to support", item)
    assert not enforce_explicit_consent("This is disappointing", item)


def test_every_factual_sentence_needs_a_citation(evidence):
    with pytest.raises(ValidationError):
        validate_grounded_answer("Delivery takes several days. Returns vary. [S1]", [evidence])


def test_history_drops_oldest_content_first():
    messages = [{"role": "user", "content": "x" * 40 + str(i)} for i in range(12)]
    summary, recent = bounded_history(messages, "", 8, 40)
    assert summary
    assert len(recent) <= 4
    assert recent[-1]["content"].endswith("11")
