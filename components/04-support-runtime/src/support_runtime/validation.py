from __future__ import annotations

import re
from typing import Any

from .domain import ACTIONS, COMPLAINT_TYPES
from .errors import ValidationError

EXPLICIT_CONSENT = re.compile(
    r"\b(?:submit|send|file|forward|report|escalate|pass)\b[^.!?\n]{0,100}"
    r"\b(?:complaint|this|it|manager|support(?: team)?)\b",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[(S\d+)\]")


def validate_message(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise ValidationError("message must be a string")
    value = value.strip()
    if not value:
        raise ValidationError("message must not be empty")
    if len(value) > limit:
        raise ValidationError(f"message exceeds {limit} characters")
    return value


def validate_decision(value: Any) -> dict[str, Any]:
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
        raise ValidationError("decision shape is invalid")
    if value["expected_action"] not in ACTIONS:
        raise ValidationError("decision action is invalid")
    if value["safety_class"] not in {"normal", "sensitive", "restricted"}:
        raise ValidationError("decision safety class is invalid")
    if not isinstance(value["rag_required"], bool):
        raise ValidationError("rag_required must be boolean")
    complaint = value["complaint"]
    if value["expected_action"] == "complaint_tool":
        validate_complaint_decision(complaint)
        if value["rag_required"]:
            raise ValidationError("complaint action cannot require RAG")
    elif complaint is not None:
        raise ValidationError("non-complaint action cannot include complaint")
    if value["expected_action"] == "rag_answer" and not value["rag_required"]:
        raise ValidationError("rag_answer must require RAG")
    return value


def validate_complaint_decision(value: Any) -> None:
    required = {
        "complaint_text",
        "category",
        "complaint_type",
        "customer_context",
        "submission_mode",
        "consent_evidence",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValidationError("complaint decision shape is invalid")
    if value["category"] != "complaint" or value["complaint_type"] not in COMPLAINT_TYPES:
        raise ValidationError("complaint taxonomy is invalid")
    text = value["complaint_text"]
    context = value["customer_context"]
    if not isinstance(text, str) or not 20 <= len(text) <= 4000:
        raise ValidationError("complaint text length is invalid")
    if not isinstance(context, str) or len(context) > 2000:
        raise ValidationError("customer context length is invalid")
    if value["submission_mode"] not in {"explicit_request", "confirmation_required"}:
        raise ValidationError("submission mode is invalid")


def enforce_explicit_consent(message: str, complaint: dict[str, Any]) -> bool:
    evidence = complaint.get("consent_evidence")
    if complaint.get("submission_mode") != "explicit_request" or not isinstance(evidence, str):
        return False
    return evidence in message and EXPLICIT_CONSENT.search(evidence) is not None
