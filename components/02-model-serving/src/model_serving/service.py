from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from .config import InferenceConfig
from .contracts import ChatRequest
from .manifest import verify_manifest
from .metrics import ServingMetrics
from .providers import ModelProvider
from .rate_limit import FixedWindowRateLimiter, RateLimitDecision


class ModelService:
    def __init__(
        self,
        provider: ModelProvider,
        config: InferenceConfig,
        *,
        git_sha: str = "development",
        model_version: str = "mock-1.0",
        manifest: dict[str, Any] | None = None,
        metrics: ServingMetrics | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.git_sha = git_sha
        self.model_version = model_version
        self.manifest = manifest
        self.metrics = metrics or ServingMetrics()
        self._ready = False
        self._probe_ok = False
        self._capacity = threading.BoundedSemaphore(config.max_concurrent_requests_per_replica)
        self._rate_limiter = FixedWindowRateLimiter(
            config.rate_limit_requests_per_window,
            config.rate_limit_window_seconds,
            config.rate_limit_max_keys,
        )

    def check_rate_limit(self, client_key: str) -> RateLimitDecision:
        return self._rate_limiter.check(client_key)

    def start(self) -> None:
        self._ready = False
        self.metrics.ready(False)
        if self.manifest is not None:
            # Re-verify at start, not only during app construction, so a
            # rotated artifact cannot become ready without a checksum check.
            verify_manifest(self.manifest)
        self.provider.load()
        probe = ChatRequest(
            ({"role": "user", "content": "readiness probe"},),
            64,
            42,
            self.config.temperature,
            self.config.top_k,
            self.config.top_p,
            self.config.min_p,
            self.config.repetition_penalty,
            self.config.stop_sequences,
            self.config.enable_thinking,
        )
        probe_output = self.provider.complete(probe).strip()
        for stop in self.config.stop_sequences:
            if stop in probe_output:
                probe_output = probe_output.split(stop, 1)[0].rstrip()
                break
        self._probe_ok = bool(probe_output)
        self._ready = self._probe_ok
        self.metrics.ready(self._ready)

    def live(self) -> dict[str, str]:
        return {"status": "live"}

    def ready(self) -> tuple[dict[str, Any], int]:
        has_capacity = self._capacity.acquire(blocking=False)
        if has_capacity:
            self._capacity.release()
        return (
            (
                {
                    "status": "ready",
                    "provider": self.provider.name,
                    "model_version": self.model_version,
                    "manifest_verified": self.manifest is not None or self.provider.name == "mock",
                },
                200,
            )
            if self._ready and self._probe_ok and has_capacity
            else ({"status": "not_ready"}, 503)
        )

    def version(self) -> dict[str, str]:
        return {
            "service": "model-serving",
            "git_sha": self.git_sha,
            "contract_version": "1.0.0",
            "model_version": self.model_version,
            "provider": self.provider.name,
        }

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._ready:
            raise RuntimeError("service is not ready")
        parsed = ChatRequest.from_openai(
            payload,
            self.config.max_new_tokens,
            default_temperature=self.config.temperature,
            default_top_k=self.config.top_k,
            default_top_p=self.config.top_p,
            default_min_p=self.config.min_p,
        )
        request = ChatRequest(
            parsed.messages,
            parsed.max_new_tokens,
            parsed.seed,
            parsed.temperature,
            parsed.top_k,
            parsed.top_p,
            parsed.min_p,
            self.config.repetition_penalty,
            self.config.stop_sequences,
            self.config.enable_thinking,
        )
        if sum(len(m["content"]) for m in request.messages) > self.config.prompt_token_limit * 2:
            raise ValueError("prompt exceeds conservative token limit")
        if not self._capacity.acquire(blocking=False):
            self.metrics.guard_failure("capacity")
            raise RuntimeError("inference capacity exhausted")
        self.metrics.queue(self.config.max_concurrent_requests_per_replica)
        try:
            started = time.monotonic()
            try:
                content = self.provider.complete(request).strip()
            except (RuntimeError, ValueError):
                raise
            except Exception as exc:
                self.metrics.guard_failure("provider_error")
                raise RuntimeError("provider request failed") from exc
            # Providers may return the template terminator in content.  Keep
            # the API response text clean while forwarding stop settings.
            for stop in self.config.stop_sequences:
                if stop in content:
                    content = content.split(stop, 1)[0].rstrip()
                    break
            if not content:
                self.metrics.guard_failure("empty_output")
                raise RuntimeError("provider returned empty output")
            if len(content) > request.max_new_tokens * 8:
                self.metrics.guard_failure("output_exhaustion")
                raise RuntimeError("provider output exhausted completion budget")
            if _has_endless_repetition(content):
                self.metrics.guard_failure("repetition")
                raise RuntimeError("provider output failed repetition guard")
            # Structured decision responses must be valid JSON objects.
            if content.startswith("{"):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as exc:
                    self.metrics.guard_failure("malformed_decision")
                    raise RuntimeError("malformed structured decision") from exc
                if not _valid_structured_decision(parsed):
                    self.metrics.guard_failure("malformed_decision")
                    raise RuntimeError("malformed structured decision")
            self.metrics.inference(
                time.monotonic() - started,
                input_tokens=sum(len(message["content"].split()) for message in request.messages),
                output_tokens=len(content.split()),
            )
            prompt_tokens = sum(len(message["content"].split()) for message in request.messages)
            completion_tokens = len(content.split())
            return {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.model_version,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            }
        finally:
            self._capacity.release()
            self.metrics.queue(0)


def _has_endless_repetition(content: str) -> bool:
    words = content.split()
    return len(words) >= 12 and len(set(words[-12:])) <= 2


def _valid_structured_decision(value: object) -> bool:
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
        return False
    if value["expected_action"] not in {
        "answer",
        "rag_answer",
        "clarify",
        "complaint_tool",
        "abstain",
    }:
        return False
    if not isinstance(value["rag_required"], bool) or value["safety_class"] not in {
        "normal",
        "sensitive",
        "restricted",
    }:
        return False
    if value["expected_action"] == "rag_answer" and not value["rag_required"]:
        return False
    if value["expected_action"] == "complaint_tool":
        complaint = value["complaint"]
        if not isinstance(complaint, dict):
            return False
        complaint_keys = {
            "complaint_text",
            "category",
            "complaint_type",
            "customer_context",
            "submission_mode",
            "consent_evidence",
        }
        return set(complaint) == complaint_keys and complaint.get("category") == "complaint"
    return value["complaint"] is None
