from __future__ import annotations

from typing import Any

import pytest
from support_runtime.config import RuntimeConfig
from support_runtime.domain import Evidence
from support_runtime.providers import StaticRetrievalProvider
from support_runtime.service import SupportRuntime
from support_runtime.storage import SQLiteRepository


class FakeModel:
    model_version = "fixture-model-1"

    def __init__(self, decision: dict[str, Any], answer: str = "General guidance."):
        self.decision = decision
        self.response = answer
        self.decide_calls = 0
        self.answer_calls = 0

    def decide(self, message: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        self.decide_calls += 1
        return self.decision

    def answer(
        self,
        message: str,
        evidence: list[Evidence],
        summary: str,
        history: list[dict[str, Any]],
    ) -> str:
        self.answer_calls += 1
        return self.response


def decision(action: str = "answer", **overrides: Any) -> dict[str, Any]:
    value = {
        "class": "general_faq",
        "intent": "general_help",
        "expected_action": action,
        "rag_required": action == "rag_answer",
        "safety_class": "normal",
        "clarification_question": None,
        "complaint": None,
    }
    value.update(overrides)
    return value


@pytest.fixture
def evidence() -> Evidence:
    return Evidence(
        "S1",
        "delivery-policy",
        "chk_1",
        "Delivery Policy",
        ["Timing"],
        "Standard delivery takes three to five business days.",
        "kb://delivery",
        "2026-09-01T00:00:00Z",
        0.9,
    )


def make_runtime(
    model: FakeModel, evidence: list[Evidence] | None = None, status: str = "ok"
) -> SupportRuntime:
    return SupportRuntime(
        SQLiteRepository(), model, StaticRetrievalProvider(evidence, status), RuntimeConfig()
    )
