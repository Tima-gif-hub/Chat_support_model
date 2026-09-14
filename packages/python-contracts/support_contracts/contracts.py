"""Generated, dependency-free views of the canonical cross-service contracts.

The JSON/YAML files under ``contracts/`` are authoritative. This module intentionally
contains only wire types and validation helpers; it does not contain runtime business logic.
``scripts/verify_contracts.py`` checks public constants against those canonical files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CONTRACT_VERSION = "1.0.0"
WORKSPACE_ID = "anonymous-furniture-company"
BUSINESS_CLASSES = frozenset(
    {
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
)
ALLOWED_ACTIONS = frozenset({"answer", "rag_answer", "clarify", "complaint_tool", "abstain"})
SAFETY_CLASSES = frozenset({"normal", "sensitive", "restricted"})
ALLOWED_COMPLAINT_TYPES = frozenset(
    {
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
)
RUNTIME_EVENTS = frozenset(
    {
        "message.accepted",
        "status",
        "token",
        "citation",
        "complaint.confirmation_required",
        "complaint.submitted",
        "completed",
        "error",
    }
)


@dataclass(frozen=True)
class Decision:
    class_name: str
    intent: str
    expected_action: str
    rag_required: bool
    safety_class: str
    clarification_question: str | None
    complaint: dict[str, Any] | None


@dataclass(frozen=True)
class RuntimeEvent:
    event: str
    request_id: str
    sequence: int
    data: dict[str, Any]


@dataclass(frozen=True)
class RetrievalEvidence:
    citation_id: str
    document_id: str
    chunk_id: str
    title: str
    heading_path: tuple[str, ...]
    content: str
    source_uri: str
    dense_score: float
    lexical_score: float
    reranker_score: float
    updated_at: str


@dataclass(frozen=True)
class RetrievalResponse:
    query_id: str
    index_version: str
    status: Literal["ok", "insufficient_evidence"]
    evidence: tuple[RetrievalEvidence, ...]


def validate_complaint_arguments(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("complaint arguments must be an object")
    required = {"complaint_text", "category", "complaint_type", "customer_context"}
    if set(value) != required:
        raise ValueError("complaint arguments have unexpected or missing fields")
    text, context = value["complaint_text"], value["customer_context"]
    if not isinstance(text, str) or not 20 <= len(text) <= 4000:
        raise ValueError("complaint_text must contain 20 to 4000 characters")
    if value["category"] != "complaint":
        raise ValueError("complaint category is invalid")
    if value["complaint_type"] not in ALLOWED_COMPLAINT_TYPES:
        raise ValueError("complaint type is invalid")
    if not isinstance(context, str) or len(context) > 2000:
        raise ValueError("customer_context must contain at most 2000 characters")
    return value


def validate_decision(value: dict[str, Any]) -> Decision:
    required = {
        "class",
        "intent",
        "expected_action",
        "rag_required",
        "safety_class",
        "clarification_question",
        "complaint",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("decision must contain exactly the canonical fields")
    if value["class"] not in BUSINESS_CLASSES or not isinstance(value["intent"], str):
        raise ValueError("unsupported decision taxonomy")
    if value["expected_action"] not in ALLOWED_ACTIONS:
        raise ValueError("unsupported expected_action")
    if not isinstance(value["rag_required"], bool):
        raise ValueError("rag_required must be boolean")
    if value["safety_class"] not in SAFETY_CLASSES:
        raise ValueError("unsupported safety_class")
    question = value["clarification_question"]
    if question is not None and (not isinstance(question, str) or len(question) > 500):
        raise ValueError("clarification_question is invalid")
    complaint = value["complaint"]
    if value["expected_action"] == "complaint_tool":
        if value["class"] != "complaint" or value["rag_required"] or question is not None:
            raise ValueError("complaint decision has inconsistent routing fields")
        if not isinstance(complaint, dict):
            raise ValueError("complaint decision requires complaint object")
        validate_complaint_decision(complaint)
    else:
        if complaint is not None:
            raise ValueError("non-complaint decision cannot carry complaint data")
        if value["expected_action"] == "rag_answer" and not value["rag_required"]:
            raise ValueError("rag_answer must require RAG")
    return Decision(
        value["class"],
        value["intent"],
        value["expected_action"],
        value["rag_required"],
        value["safety_class"],
        question,
        complaint,
    )


def validate_complaint_decision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("complaint decision requires an object")
    required = {
        "complaint_text",
        "category",
        "complaint_type",
        "customer_context",
        "submission_mode",
        "consent_evidence",
    }
    if set(value) != required:
        raise ValueError("complaint decision has unexpected or missing fields")
    validate_complaint_arguments(
        {
            key: value[key]
            for key in ("complaint_text", "category", "complaint_type", "customer_context")
        }
    )
    if value["submission_mode"] not in {"explicit_request", "confirmation_required"}:
        raise ValueError("invalid submission mode")
    evidence = value["consent_evidence"]
    if value["submission_mode"] == "explicit_request" and (
        not isinstance(evidence, str) or not evidence
    ):
        raise ValueError("explicit request requires consent evidence")
    if value["submission_mode"] == "confirmation_required" and evidence is not None:
        raise ValueError("confirmation-required complaint cannot contain consent evidence")
    return value


def validate_runtime_event(value: Any) -> RuntimeEvent:
    if not isinstance(value, dict) or set(value) != {"event", "request_id", "sequence", "data"}:
        raise ValueError("runtime event shape is invalid")
    event, request_id, sequence, data = (
        value["event"],
        value["request_id"],
        value["sequence"],
        value["data"],
    )
    if event not in RUNTIME_EVENTS or not isinstance(request_id, str):
        raise ValueError("runtime event identity is invalid")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("runtime event sequence must be a positive integer")
    if not isinstance(data, dict):
        raise ValueError("runtime event data must be an object")
    required_by_event = {
        "message.accepted": {"message_id"},
        "status": {"state"},
        "token": {"text"},
        "citation": {"citation_id", "title", "heading_path", "source_uri", "updated_at"},
        "complaint.confirmation_required": {"draft_id", "complaint_text", "complaint_type"},
        "complaint.submitted": {"complaint_id", "status", "duplicate", "created_at"},
        "completed": {"outcome"},
        "error": {"code", "message", "retryable"},
    }
    if not required_by_event[event] <= data.keys():
        raise ValueError(f"{event} event data is incomplete")
    return RuntimeEvent(event, request_id, sequence, data)


def validate_retrieval_response(value: Any) -> RetrievalResponse:
    if not isinstance(value, dict) or set(value) != {
        "query_id",
        "index_version",
        "status",
        "evidence",
    }:
        raise ValueError("retrieval response shape is invalid")
    if value["status"] not in {"ok", "insufficient_evidence"} or not isinstance(
        value["evidence"], list
    ):
        raise ValueError("retrieval response status is invalid")
    evidence: list[RetrievalEvidence] = []
    required = {
        "citation_id",
        "document_id",
        "chunk_id",
        "title",
        "heading_path",
        "content",
        "source_uri",
        "dense_score",
        "lexical_score",
        "reranker_score",
        "updated_at",
    }
    for item in value["evidence"]:
        if not isinstance(item, dict) or not required <= item.keys():
            raise ValueError("retrieval evidence shape is invalid")
        if not isinstance(item["heading_path"], list) or not all(
            isinstance(x, str) for x in item["heading_path"]
        ):
            raise ValueError("retrieval heading_path is invalid")
        evidence.append(RetrievalEvidence(**{key: item[key] for key in required}))
    if (
        len(evidence) > 5
        or (value["status"] == "ok" and not evidence)
        or (value["status"] == "insufficient_evidence" and evidence)
    ):
        raise ValueError("retrieval status and evidence are inconsistent")
    return RetrievalResponse(
        value["query_id"], value["index_version"], value["status"], tuple(evidence)
    )
