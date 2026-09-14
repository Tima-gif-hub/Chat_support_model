from __future__ import annotations

import html
import re

_ACTIVE_BLOCKS = re.compile(
    r"<(script|style|iframe|object|embed|form)[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_TAGS = re.compile(r"<[^>]+>")
_INJECTION = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|system\s+prompt|"
    r"developer\s+message|act\s+as\s+|execute\s+(?:this|the)\s+instruction|"
    r"reveal\s+(?:secrets?|credentials?|prompts?))",
    re.IGNORECASE,
)


def sanitize_html(value: str) -> str:
    value = _ACTIVE_BLOCKS.sub(" ", value)
    value = _TAGS.sub(" ", value)
    return html.unescape(value)


def contains_instructional_injection(value: str) -> bool:
    """Reject source text that tries to turn evidence into executable instructions."""

    return bool(_INJECTION.search(value))
