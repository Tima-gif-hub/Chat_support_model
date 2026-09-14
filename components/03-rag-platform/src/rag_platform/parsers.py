from __future__ import annotations

import json
from pathlib import Path

from .security import sanitize_html


class ParseError(ValueError):
    pass


def parse_source(path: Path) -> tuple[dict[str, object], str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict):
            raise ParseError(f"{path.name}: expected metadata object")
        content = payload.get("content")
        if isinstance(content, list):
            content = "\n\n".join(str(part) for part in content)
        if not isinstance(content, str):
            raise ParseError(f"{path.name}: expected string or list content")
        return payload["metadata"], content
    if suffix in {".md", ".txt", ".html", ".htm"}:
        raw = path.read_text(encoding="utf-8")
        if raw.startswith("---\n"):
            end = raw.find("\n---\n", 4)
            if end < 0:
                raise ParseError(f"{path.name}: unterminated metadata header")
            metadata = _simple_yaml(raw[4:end])
            raw = raw[end + 5 :]
        else:
            raise ParseError(f"{path.name}: text sources require a metadata header")
        return metadata, sanitize_html(raw) if suffix in {".html", ".htm"} else raw
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ParseError("PDF ingestion requires the optional pypdf package") from exc
        reader = PdfReader(str(path))
        metadata = {str(k).lstrip("/"): str(v) for k, v in (reader.metadata or {}).items()}
        return metadata, "\n\n".join(page.extract_text() or "" for page in reader.pages)
    raise ParseError(f"unsupported source format: {suffix}")


def _simple_yaml(raw: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ParseError(f"invalid metadata line: {line}")
        result[key.strip()] = value.strip().strip('"').strip("'") or None
    return result
