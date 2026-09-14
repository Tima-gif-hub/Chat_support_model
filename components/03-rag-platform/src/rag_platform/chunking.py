from __future__ import annotations

import hashlib
import re

from .config import RagConfig
from .models import Chunk, Document

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def chunk_document(document: Document, index_version: str, config: RagConfig) -> list[Chunk]:
    units = _units(document.content)
    chunks: list[tuple[tuple[str, ...], list[str]]] = []
    current: list[str] = []
    current_path: tuple[str, ...] = ()
    for heading_path, unit in units:
        unit_tokens = unit.split()
        if current and (
            heading_path != current_path or len(current) + len(unit_tokens) > config.target_tokens
        ):
            chunks.extend(_bounded(current_path, current, config))
            current = []
        current_path = heading_path
        current.extend(unit_tokens)
    if current:
        chunks.extend(_bounded(current_path, current, config))

    result: list[Chunk] = []
    offset = 0
    for sequence, (heading_path, words) in enumerate(chunks):
        content = " ".join(words)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        result.append(
            Chunk(
                chunk_id=f"chk_{document.document_id}_{sequence:03d}_{digest[:12]}",
                document_id=document.document_id,
                index_version=index_version,
                title=document.title,
                heading_path=heading_path,
                content=content,
                token_start=offset,
                token_end=offset + len(words),
                content_sha256=digest,
                workspace_id=document.workspace_id,
                audience=document.audience,
                language=document.language,
                effective_from=document.effective_from,
                effective_to=document.effective_to,
                updated_at=document.updated_at,
                source_uri=document.source_uri,
            )
        )
        offset += max(1, len(words) - config.overlap_tokens)
    return result


def _units(content: str) -> list[tuple[tuple[str, ...], str]]:
    headings: list[str] = []
    units: list[tuple[tuple[str, ...], str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            units.append((tuple(headings), " ".join(paragraph)))
            paragraph.clear()

    for line in content.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            headings[level - 1 :] = [match.group(2)]
        elif line.strip():
            # A Markdown table row remains indivisible and retains its preceding heading context.
            paragraph.append(line.strip())
        else:
            flush()
    flush()
    return units or [((), content)]


def _bounded(
    heading_path: tuple[str, ...], words: list[str], config: RagConfig
) -> list[tuple[tuple[str, ...], list[str]]]:
    if len(words) <= config.maximum_tokens:
        return [(heading_path, words)]
    result: list[tuple[tuple[str, ...], list[str]]] = []
    step = config.maximum_tokens - config.overlap_tokens
    for start in range(0, len(words), step):
        part = words[start : start + config.maximum_tokens]
        if len(part) < config.minimum_tokens and result:
            result[-1][1].extend(part)
            result[-1][1][:] = result[-1][1][: config.maximum_tokens]
            break
        result.append((heading_path, part))
        if start + config.maximum_tokens >= len(words):
            break
    return result
