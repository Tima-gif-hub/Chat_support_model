from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .contracts import ChatRequest


class ModelProvider(Protocol):
    name: str

    def load(self) -> None: ...
    def complete(self, request: ChatRequest) -> str: ...


class DeterministicMockProvider:
    name = "mock"

    def __init__(self) -> None:
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def complete(self, request: ChatRequest) -> str:
        if not self.loaded:
            raise RuntimeError("provider is not loaded")
        text = next((m["content"] for m in reversed(request.messages) if m["role"] == "user"), "")
        system_text = "\n".join(m["content"] for m in request.messages if m["role"] == "system")
        if "Cite every company-factual" in system_text:
            evidence = re.findall(
                r"<(S\d+)>\s*(.*?)\s*</\1>", system_text, re.DOTALL | re.IGNORECASE
            )
            if evidence:
                parts = []
                for citation_id, block in evidence[:2]:
                    sentence = re.split(r"(?<=[.!?])\s+", " ".join(block.split()))[0].strip(" .")
                    if sentence:
                        parts.append(f"{sentence} [{citation_id.upper()}].")
                if parts:
                    return " ".join(parts)
        lowered = text.casefold()
        delivery_delay = "delivery" in lowered and any(
            word in lowered for word in ("late", "delay", "overdue", "frustrat", "not arrived")
        )
        delivery_damage = "delivery" in lowered and any(
            word in lowered for word in ("damaged", "broken", "damage")
        )
        if (
            delivery_delay
            or delivery_damage
            or any(word in lowered for word in ("complaint", "damaged", "broken"))
        ):
            complaint_type = (
                "delivery_delay"
                if delivery_delay
                else "delivery_damage"
                if delivery_damage
                else "product_quality"
            )
            complaint_text = text if len(text) >= 20 else f"{text} Please help."
            explicit_evidence = _explicit_consent_evidence(text)
            result = {
                "class": "complaint",
                "intent": complaint_type,
                "expected_action": "complaint_tool",
                "rag_required": False,
                "safety_class": "normal",
                "clarification_question": None,
                "complaint": {
                    "complaint_text": complaint_text,
                    "category": "complaint",
                    "complaint_type": complaint_type,
                    "customer_context": "Customer reported this issue in the current message.",
                    "submission_mode": "explicit_request"
                    if explicit_evidence
                    else "confirmation_required",
                    "consent_evidence": explicit_evidence,
                },
            }
        elif any(
            word in lowered for word in ("price", "delivery", "warranty", "material", "stock")
        ):
            result = {
                "class": "catalog",
                "intent": "company_fact",
                "expected_action": "rag_answer",
                "rag_required": True,
                "safety_class": "normal",
                "clarification_question": None,
                "complaint": None,
            }
        elif any(
            word in lowered
            for word in ("weather", "medical", "password", "private", "salary", "internal")
        ):
            result = {
                "class": "other_out_of_scope",
                "intent": "unsupported",
                "expected_action": "abstain",
                "rag_required": False,
                "safety_class": "restricted",
                "clarification_question": None,
                "complaint": None,
            }
        else:
            # Stable hash makes the simulator varied while remaining reproducible.
            action = (
                "answer"
                if int(hashlib.sha256(lowered.encode()).hexdigest()[:2], 16) % 2
                else "clarify"
            )
            result = {
                "class": "general_faq",
                "intent": "general_help",
                "expected_action": action,
                "rag_required": False,
                "safety_class": "normal",
                "clarification_question": "Which product can I help with?"
                if action == "clarify"
                else None,
                "complaint": None,
            }
        return json.dumps(result, sort_keys=True, separators=(",", ":"))


def _explicit_consent_evidence(message: str) -> str | None:
    match = re.search(
        r"\b(?:submit|send|file|forward|report|escalate|pass)\b[^.!?\n]{0,100}"
        r"\b(?:complaint|this|it|manager|support(?: team)?)\b",
        message,
        re.IGNORECASE,
    )
    return match.group(0) if match else None


@dataclass
class OpenAICompatibleProvider:
    endpoint: str
    model: str
    timeout_seconds: int = 30
    name: str = "external_openai_compatible"

    def load(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("provider endpoint must be HTTP(S)")

    def complete(self, request: ChatRequest) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": request.messages,
                "max_tokens": request.max_new_tokens,
                # Forward the complete controlled sampling contract.  vLLM
                # accepts these OpenAI-compatible fields and external
                # providers can reject unsupported values explicitly.
                "temperature": request.temperature,
                "top_k": request.top_k,
                "top_p": request.top_p,
                "min_p": request.min_p,
                "repetition_penalty": request.repetition_penalty,
                "stop": list(request.stop_sequences),
                "chat_template_kwargs": {"enable_thinking": request.enable_thinking},
                "seed": request.seed,
            }
        ).encode()
        endpoint = self.endpoint.rstrip("/")
        if not endpoint.endswith("/v1"):
            endpoint += "/v1"
        http_request = urllib.request.Request(
            endpoint + "/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:  # noqa: S310
            body = json.load(response)
        return str(body["choices"][0]["message"]["content"])


class VllmProvider(OpenAICompatibleProvider):
    def __init__(self, endpoint: str, model: str, timeout_seconds: int = 30) -> None:
        super().__init__(endpoint, model, timeout_seconds, name="vllm")


def create_provider(
    provider: str,
    *,
    endpoint: str | None = None,
    model: str = "Qwen/Qwen3-4B",
    timeout_seconds: int = 30,
) -> ModelProvider:
    """Create one of the three supported serving adapters."""
    if provider == "mock":
        return DeterministicMockProvider()
    if provider == "vllm":
        if not endpoint:
            raise ValueError("MODEL_ENDPOINT is required for vllm provider")
        return VllmProvider(endpoint, model, timeout_seconds)
    if provider in {"external", "external_openai_compatible"}:
        if not endpoint:
            raise ValueError("MODEL_ENDPOINT is required for external provider")
        return OpenAICompatibleProvider(endpoint, model, timeout_seconds)
    raise ValueError(f"unsupported model provider: {provider}")
