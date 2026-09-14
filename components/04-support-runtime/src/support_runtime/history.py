from __future__ import annotations

from typing import Any


def approximate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def bounded_history(
    messages: list[dict[str, Any]], existing_summary: str, turn_limit: int, token_limit: int
) -> tuple[str, list[dict[str, Any]]]:
    recent = messages[-turn_limit:]
    while (
        recent and sum(approximate_tokens(str(m.get("content", ""))) for m in recent) > token_limit
    ):
        recent.pop(0)
    older = messages[: max(0, len(messages) - len(recent))]
    if not older:
        return existing_summary, recent
    fragments = [existing_summary] if existing_summary else []
    for item in older:
        role = item.get("role", "unknown")
        content = " ".join(str(item.get("content", "")).split())[:240]
        fragments.append(f"{role}: {content}")
    summary = " | ".join(filter(None, fragments))
    return summary[-2400:], recent
