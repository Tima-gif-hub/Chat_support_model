from __future__ import annotations

import json
from typing import Any


def decision_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """Build the exact decision contract consumed by support-runtime.

    ``tool_call`` is an annotation on a canonical training record.  It is not
    the runtime decision contract and must never be rendered as an executable
    tool call.  In particular, consent state is retained in the complaint
    object so the runtime can enforce it again.
    """
    expected_action = record["expected_action"]
    complaint = None
    if expected_action == "complaint_tool":
        tool = record.get("tool_call") or {}
        arguments = tool.get("arguments") if isinstance(tool, dict) else None
        arguments = arguments if isinstance(arguments, dict) else {}
        complaint = {
            "complaint_text": str(arguments.get("complaint_text") or record["answer"]),
            "category": "complaint",
            "complaint_type": record.get("complaint_type") or arguments.get("complaint_type"),
            "customer_context": str(arguments.get("customer_context") or ""),
            "submission_mode": arguments.get("submission_mode", "confirmation_required"),
            "consent_evidence": arguments.get("consent_evidence"),
        }
    return {
        "class": record["class"],
        "intent": record["intent"],
        "expected_action": expected_action,
        "rag_required": bool(record["rag_required"]),
        "safety_class": record["safety_class"],
        "clarification_question": record.get("clarification_question"),
        "complaint": complaint,
    }


def render_training_example(record: dict[str, Any], token_budget: int = 8192) -> str:
    decision = decision_from_record(record)
    assistant = (
        json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n" + record["answer"]
    )
    rendered = (
        "<|im_start|>system\nYou are a concise furniture customer-support assistant."
        " Thinking is disabled.<|im_end|>\n"
        f"<|im_start|>user\n{record['question']}<|im_end|>\n"
        f"<|im_start|>assistant\n{assistant}<|im_end|>\n"
    )
    # The CPU path deliberately uses a conservative character bound and does not load a tokenizer.
    if len(rendered) > token_budget * 2:
        raise ValueError("rendered example exceeds conservative token budget")
    return rendered
