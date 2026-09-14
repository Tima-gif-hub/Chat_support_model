import json
from pathlib import Path

from support_contracts import validate_decision

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_json_contracts_parse() -> None:
    for path in (ROOT / "contracts").glob("*.schema.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_complaint_decision_contract_accepts_confirmation() -> None:
    decision = {
        "class": "complaint",
        "intent": "delivery_delay",
        "expected_action": "complaint_tool",
        "rag_required": False,
        "safety_class": "normal",
        "clarification_question": None,
        "complaint": {
            "complaint_text": "My delivery is five days late and I need help.",
            "category": "complaint",
            "complaint_type": "delivery_delay",
            "customer_context": "",
            "submission_mode": "confirmation_required",
            "consent_evidence": None,
        },
    }
    assert validate_decision(decision).complaint["complaint_type"] == "delivery_delay"
