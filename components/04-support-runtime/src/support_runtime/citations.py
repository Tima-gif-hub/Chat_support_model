from __future__ import annotations

import re

from .domain import Evidence
from .errors import ValidationError
from .validation import CITATION

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def validate_grounded_answer(answer: str, evidence: list[Evidence]) -> tuple[str, list[Evidence]]:
    allowed = {item.citation_id: item for item in evidence}
    used = CITATION.findall(answer)
    if not used:
        raise ValidationError("grounded answer has no citations")
    unknown = set(used) - set(allowed)
    if unknown:
        raise ValidationError("grounded answer contains unknown citations")
    # Accept both common placements: "fact [S1]." and "fact. [S1]".
    citation_attached = re.sub(r"([.!?])\s+(\[S\d+\])", r" \2\1", answer.strip())
    for sentence in SENTENCE.split(citation_attached):
        words = re.findall(r"[A-Za-z0-9]+", sentence)
        if len(words) >= 4 and not CITATION.search(sentence):
            raise ValidationError("company-specific sentence lacks a citation")
    unique = list(dict.fromkeys(used))
    return answer, [allowed[citation_id] for citation_id in unique]
