from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLASSES = {
    "availability",
    "catalog",
    "pricing",
    "payment",
    "order",
    "delivery",
    "returns",
    "warranty",
    "assembly_service",
    "complaint",
    "account_privacy",
    "general_faq",
    "other_out_of_scope",
}
ACTIONS = {"answer", "rag_answer", "clarify", "complaint_tool", "abstain"}
SAFETY_CLASSES = {"normal", "sensitive", "restricted"}
COMPLAINT_TYPES = {
    "waiting_time",
    "product_quality",
    "price",
    "delivery_delay",
    "delivery_damage",
    "wrong_item",
    "missing_item_or_part",
    "payment_issue",
    "return_or_refund",
    "service_quality",
    "staff_interaction",
    "availability_or_stock",
    "other",
}
REQUIRED_FIELDS = {
    "record_id",
    "question",
    "answer",
    "class",
    "intent",
    "rag_required",
    "expected_action",
    "safety_class",
    "tool_call",
    "complaint_type",
    "language",
    "source",
    "source_record_id",
    "semantic_cluster_id",
    "synthetic_data",
    "review_status",
    "provenance",
}

# The decision object is deliberately kept in lock-step with
# ``contracts/decision.schema.json``.  Training examples contain the source
# ``tool_call`` shape, while the model must emit the runtime ``complaint``
# shape; the renderer performs that conversion (see render.py).
DECISION_ACTIONS = ACTIONS


@dataclass(frozen=True)
class ValidationError:
    record_id: str
    reason: str


def validate_record(record: dict[str, Any]) -> None:
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if not all(
        isinstance(record[key], str) and record[key].strip()
        for key in ("record_id", "question", "answer", "intent", "source", "semantic_cluster_id")
    ):
        raise ValueError("required text fields must be non-empty strings")
    if record["class"] not in CLASSES:
        raise ValueError("unsupported class")
    if record["expected_action"] not in ACTIONS:
        raise ValueError("unsupported expected_action")
    if record["safety_class"] not in SAFETY_CLASSES:
        raise ValueError("unsupported safety_class")
    if record["language"] != "en":
        raise ValueError("public training fixture supports English only")
    if not isinstance(record["rag_required"], bool) or not isinstance(
        record["synthetic_data"], bool
    ):
        raise ValueError("rag_required and synthetic_data must be booleans")
    if record["expected_action"] == "rag_answer" and not record["rag_required"]:
        raise ValueError("rag_answer requires rag_required=true")
    if record["expected_action"] in {"answer", "clarify", "abstain", "complaint_tool"} and record[
        "rag_required"
    ]:
        raise ValueError("non-RAG action cannot require RAG")
    provenance = record["provenance"]
    if (
        not isinstance(provenance, dict)
        or not {"dataset_name", "license", "collected_at"} <= provenance.keys()
    ):
        raise ValueError("invalid provenance")
    is_complaint = record["expected_action"] == "complaint_tool"
    if is_complaint:
        if record["class"] != "complaint" or record["complaint_type"] not in COMPLAINT_TYPES:
            raise ValueError("complaint action requires complaint class and subtype")
        tool = record["tool_call"]
        if not isinstance(tool, dict) or tool.get("name") != "submit_complaint":
            raise ValueError("complaint action requires submit_complaint tool call")
        arguments = tool.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("complaint tool arguments must be an object")
        if arguments.get("submission_mode") not in {
            "explicit_request",
            "confirmation_required",
        }:
            raise ValueError("complaint tool requires a consent-aware submission mode")
        if arguments.get("complaint_type", record["complaint_type"]) != record["complaint_type"]:
            raise ValueError("complaint subtype must agree with tool arguments")
    elif record["tool_call"] is not None or record["complaint_type"] is not None:
        raise ValueError("non-complaint record cannot include complaint data")
