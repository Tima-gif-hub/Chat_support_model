from __future__ import annotations

import re

from .models import RetrievalResponse

_CITATION = re.compile(r"\[(S\d+)\]")


class CitationError(ValueError):
    pass


def validate_citations(answer: str, retrieval: RetrievalResponse) -> tuple[str, tuple[str, ...]]:
    allowed = {item.citation_id for item in retrieval.evidence}
    used = tuple(dict.fromkeys(_CITATION.findall(answer)))
    unknown = set(used) - allowed
    if unknown:
        raise CitationError(f"unknown citation IDs: {', '.join(sorted(unknown))}")
    factual_sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", answer) if part.strip()
    ]
    for sentence in factual_sentences:
        if sentence.endswith("?") or not re.search(r"[A-Za-z]", sentence):
            continue
        if not _CITATION.search(sentence):
            raise CitationError("each company-specific factual sentence requires a citation")
    return answer, used


def used_evidence(retrieval: RetrievalResponse, citation_ids: tuple[str, ...]):
    wanted = set(citation_ids)
    return tuple(item for item in retrieval.evidence if item.citation_id in wanted)
