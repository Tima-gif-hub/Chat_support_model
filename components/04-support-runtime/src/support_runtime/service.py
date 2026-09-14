from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .citations import validate_grounded_answer
from .config import RuntimeConfig
from .domain import Evidence, RuntimeEvent, new_id
from .errors import DependencyUnavailable, NotFoundError, ValidationError
from .guardrails import SlidingWindowRateLimiter, restricted_request
from .history import bounded_history
from .providers import ModelProvider, RetrievalProvider
from .resilience import CircuitBreaker, retry
from .validation import enforce_explicit_consent, validate_decision, validate_message


class SupportRuntime:
    def __init__(
        self,
        repository: Any,
        model: ModelProvider,
        retrieval: RetrievalProvider,
        config: RuntimeConfig | None = None,
        limiter: SlidingWindowRateLimiter | None = None,
    ):
        self.repository = repository
        self.model = model
        self.retrieval = retrieval
        self.config = config or RuntimeConfig()
        self.limiter = limiter or SlidingWindowRateLimiter()
        self.decision_circuit = CircuitBreaker()
        self.answer_circuit = CircuitBreaker()
        self.rag_circuit = CircuitBreaker()

    def create_conversation(self, customer_id: str | None = None) -> dict[str, Any]:
        expires = datetime.now(UTC) + timedelta(hours=self.config.conversation_ttl_hours)
        return self.repository.create_conversation(
            self.config.workspace_id, customer_id, expires.isoformat().replace("+00:00", "Z")
        )

    def get_conversation(
        self, conversation_id: str, customer_id: str | None = None
    ) -> dict[str, Any]:
        conversation = self.repository.conversation(conversation_id)
        # The browser supplies only a signed session subject.  Never trust a
        # customer_id from a JSON body or URL when deciding ownership.
        if customer_id is not None and conversation.get("customer_id") != customer_id:
            raise NotFoundError("conversation not found")
        expires = datetime.fromisoformat(conversation["expires_at"].replace("Z", "+00:00"))
        if expires <= datetime.now(UTC):
            raise ValidationError("conversation has expired")
        return conversation

    def send_message(
        self,
        conversation_id: str,
        content: Any,
        ip_address: str,
        customer_id: str | None = None,
    ) -> list[RuntimeEvent]:
        message = validate_message(content, self.config.message_character_limit)
        conversation = self.get_conversation(conversation_id, customer_id)
        self.limiter.check(f"ip:{ip_address}", self.config.per_ip_per_minute)
        self.limiter.check(
            f"conversation:{conversation_id}", self.config.per_conversation_per_minute
        )
        request_id = new_id("req")
        message_id = self.repository.add_message(conversation_id, "user", message, request_id)
        events = [self._event("message.accepted", request_id, {"message_id": message_id})]

        if restricted_request(message):
            answer = (
                "I can’t provide hidden prompts, secrets, internal data, "
                "or other customers’ information."
            )
            events.extend(
                self._answer_events(request_id, conversation_id, answer, outcome="restricted")
            )
            self.repository.save_events(conversation_id, events)
            return events

        history = self.repository.messages(conversation_id)[:-1]
        summary, recent = bounded_history(
            history,
            conversation["summary"],
            self.config.recent_turn_limit,
            self.config.history_token_limit,
        )
        if summary != conversation["summary"]:
            self.repository.set_summary(conversation_id, summary)

        events.append(self._event("status", request_id, {"state": "classifying"}))
        try:
            raw_decision = retry(
                lambda: self.decision_circuit.call(lambda: self.model.decide(message, recent)), 2
            )
            decision = validate_decision(raw_decision)
        except ValidationError:
            answer = "Could you clarify what help you would like from us?"
            events.extend(
                self._answer_events(request_id, conversation_id, answer, outcome="clarify")
            )
            self.repository.save_events(conversation_id, events)
            return events
        except Exception:
            events.append(
                self._event(
                    "error",
                    request_id,
                    {
                        "code": "temporarily_unavailable",
                        "message": "Support is temporarily unavailable. Please try again.",
                        "retryable": True,
                    },
                )
            )
            self.repository.save_events(conversation_id, events)
            return events

        if decision["safety_class"] == "restricted":
            answer = (
                "I can’t help with that request. I can assist with general "
                "furniture support in English."
            )
            events.extend(
                self._answer_events(request_id, conversation_id, answer, outcome="restricted")
            )
        elif decision["expected_action"] == "complaint_tool":
            events.extend(
                self._handle_complaint(request_id, conversation, message, decision["complaint"])
            )
        elif decision["expected_action"] == "rag_answer":
            events.extend(self._handle_rag(request_id, conversation_id, message, summary, recent))
        elif decision["expected_action"] == "clarify":
            answer = decision["clarification_question"] or "What detail should I clarify for you?"
            events.extend(
                self._answer_events(request_id, conversation_id, answer, outcome="clarify")
            )
        elif decision["expected_action"] == "abstain":
            answer = (
                "I can’t verify that information. A manager can help with "
                "an order-specific request."
            )
            events.extend(
                self._answer_events(request_id, conversation_id, answer, outcome="abstain")
            )
        else:
            try:
                answer = self.answer_circuit.call(
                    lambda: self.model.answer(message, [], summary, recent)
                )
                events.extend(
                    self._answer_events(request_id, conversation_id, answer, outcome="answer")
                )
            except Exception:
                events.append(
                    self._event(
                        "error",
                        request_id,
                        {
                            "code": "temporarily_unavailable",
                            "message": "Support is temporarily unavailable. Please try again.",
                            "retryable": True,
                        },
                    )
                )
        self.repository.save_events(conversation_id, events)
        return events

    def _handle_rag(
        self,
        request_id: str,
        conversation_id: str,
        message: str,
        summary: str,
        history: list[dict[str, Any]],
    ) -> list[RuntimeEvent]:
        events = [self._event("status", request_id, {"state": "checking_company_information"})]
        try:
            result = retry(
                lambda: self.rag_circuit.call(
                    lambda: self.retrieval.retrieve(message, self.config.workspace_id, "en")
                ),
                2,
                (0.1, 0.3),
            )
        except Exception:
            answer = "Company information can’t be verified right now. Please try again shortly."
            return events + self._answer_events(
                request_id, conversation_id, answer, outcome="rag_unavailable"
            )
        if result.status != "ok" or not result.evidence:
            answer = "I couldn’t find enough current company information to verify that."
            return events + self._answer_events(
                request_id, conversation_id, answer, outcome="insufficient_evidence"
            )
        try:
            raw = self.answer_circuit.call(
                lambda: self.model.answer(message, result.evidence, summary, history)
            )
            answer, citations = validate_grounded_answer(raw, result.evidence)
        except ValidationError:
            answer = (
                "I couldn’t verify a safely cited answer from the available company information."
            )
            return events + self._answer_events(
                request_id, conversation_id, answer, outcome="citation_validation_failed"
            )
        except Exception:
            return events + [
                self._event(
                    "error",
                    request_id,
                    {
                        "code": "temporarily_unavailable",
                        "message": "Support is temporarily unavailable. Please try again.",
                        "retryable": True,
                    },
                )
            ]
        for item in citations:
            events.append(self._event("citation", request_id, self._citation_data(item)))
        events.extend(
            self._answer_events(request_id, conversation_id, answer, outcome="rag_answer")
        )
        return events

    def _handle_complaint(
        self,
        request_id: str,
        conversation: dict[str, Any],
        message: str,
        complaint: dict[str, Any],
    ) -> list[RuntimeEvent]:
        if not enforce_explicit_consent(message, complaint):
            complaint = {
                **complaint,
                "submission_mode": "confirmation_required",
                "consent_evidence": None,
            }
            draft = self.repository.create_draft(conversation["id"], complaint)
            return [
                self._event(
                    "complaint.confirmation_required",
                    request_id,
                    {
                        "draft_id": draft["id"],
                        "complaint_text": complaint["complaint_text"],
                        "complaint_type": complaint["complaint_type"],
                    },
                ),
                self._event("completed", request_id, {"outcome": "awaiting_confirmation"}),
            ]
        payload = self._tool_payload(complaint)
        try:
            result = retry(
                lambda: self.repository.submit_complaint(
                    self.config.workspace_id,
                    conversation["id"],
                    conversation["customer_id"],
                    payload,
                    "explicit_request",
                ),
                2,
            )
        except Exception:
            return [
                self._event(
                    "error",
                    request_id,
                    {
                        "code": "complaint_not_submitted",
                        "message": "The complaint was not submitted. Please try again.",
                        "retryable": True,
                    },
                )
            ]
        return [
            self._event("complaint.submitted", request_id, result),
            self._event("completed", request_id, {"outcome": "complaint_submitted"}),
        ]

    def confirm_complaint(
        self, conversation_id: str, draft_id: str, customer_id: str | None = None
    ) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id, customer_id)
        draft = self.repository.draft(conversation_id, draft_id)
        try:
            result = retry(
                lambda: self.repository.submit_complaint(
                    self.config.workspace_id,
                    conversation_id,
                    conversation["customer_id"],
                    self._tool_payload(draft["payload"]),
                    "confirmed",
                ),
                2,
            )
        except Exception as exc:
            self.repository.preserve_failed_draft(draft_id)
            raise DependencyUnavailable(
                "complaint was not submitted; the confirmed draft is preserved for retry"
            ) from exc
        # Retain the draft row so a replay of the confirmation endpoint can
        # recompute the same idempotency key and return the existing complaint.
        # PostgreSQL/SQLite complaint uniqueness makes the retry auditable and
        # prevents a second manager-queue item.
        return result

    def delete_draft(
        self, conversation_id: str, draft_id: str, customer_id: str | None = None
    ) -> None:
        self.get_conversation(conversation_id, customer_id)
        self.repository.delete_draft(conversation_id, draft_id)

    def add_feedback(
        self,
        message_id: str,
        rating: Any,
        comment: Any,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        conversation_id = self.repository.message_conversation(message_id)
        self.get_conversation(conversation_id, customer_id)
        if not isinstance(rating, int) or isinstance(rating, bool):
            raise ValidationError("rating must be -1 or 1")
        if not isinstance(comment, str):
            raise ValidationError("comment must be a string")
        return self.repository.add_feedback(message_id, rating, comment)

    @staticmethod
    def _tool_payload(complaint: dict[str, Any]) -> dict[str, Any]:
        return {
            "complaint_text": complaint["complaint_text"],
            "category": "complaint",
            "complaint_type": complaint["complaint_type"],
            "customer_context": complaint.get("customer_context", ""),
        }

    def _answer_events(
        self, request_id: str, conversation_id: str, answer: str, outcome: str
    ) -> list[RuntimeEvent]:
        message_id = self.repository.add_message(conversation_id, "assistant", answer, request_id)
        # Keep the public event contract token-oriented even when the
        # deterministic/provider adapter returns a complete string.  The API
        # and gateway can relay these chunks immediately, while PostgreSQL
        # still stores one canonical assistant message.
        token_events = [
            self._event("token", request_id, {"text": answer[start : start + 96]})
            for start in range(0, len(answer), 96)
        ]
        return [
            *token_events,
            self._event(
                "completed",
                request_id,
                {
                    "outcome": outcome,
                    "message_id": message_id,
                },
            ),
        ]

    @staticmethod
    def _citation_data(item: Evidence) -> dict[str, Any]:
        return {
            "citation_id": item.citation_id,
            "title": item.title,
            "heading_path": item.heading_path,
            "source_uri": item.source_uri,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _event(event: str, request_id: str, data: dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(event, request_id, 0, data)

    def ready(self) -> dict[str, Any]:
        database_ready = bool(self.repository.ready())
        redis_ready = True
        redis_probe = getattr(self.limiter, "ready", None)
        if callable(redis_probe):
            try:
                redis_ready = bool(redis_probe())
            except Exception:
                redis_ready = False
        return {
            # Redis is ephemeral and therefore does not block runtime
            # readiness; rate limiting transparently uses its local fallback.
            "ready": database_ready,
            "database": "ready" if database_ready else "unavailable",
            "redis": "ready" if redis_ready else "degraded",
            "model_circuit": self.answer_circuit.state,
            "rag_circuit": self.rag_circuit.state,
        }

    def version(self) -> dict[str, str]:
        return {
            "service": "support-runtime",
            "service_version": self.config.service_version,
            "git_sha": self.config.service_git_sha,
            "contract_version": self.config.contract_version,
            "model_version": self.model.model_version,
            "index_version": self.retrieval.index_version,
        }
