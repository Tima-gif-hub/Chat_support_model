from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

COMPLAINT_TYPES = frozenset(
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
ACTIONS = frozenset({"answer", "rag_answer", "clarify", "complaint_tool", "abstain"})


def new_id(prefix: str) -> str:
    # UUID is storage-safe and sortable IDs can be swapped in without changing contracts.
    return f"{prefix}_{uuid4().hex}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Evidence:
    citation_id: str
    document_id: str
    chunk_id: str
    title: str
    heading_path: list[str]
    content: str
    source_uri: str
    updated_at: str
    reranker_score: float = 0.0


@dataclass(frozen=True)
class RetrievalResult:
    query_id: str
    index_version: str
    status: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class RuntimeEvent:
    event: str
    request_id: str
    sequence: int
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "request_id": self.request_id,
            "sequence": self.sequence,
            "data": self.data,
        }


def is_public_id(value: str, prefix: str) -> bool:
    if not value.startswith(prefix + "_"):
        return False
    try:
        UUID(value[len(prefix) + 1 :])
    except ValueError:
        return len(value[len(prefix) + 1 :]) == 32
    return True
