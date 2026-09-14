from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    workspace_id: str = "anonymous-furniture-company"
    message_character_limit: int = 8_000
    recent_turn_limit: int = 8
    history_token_limit: int = 2_400
    conversation_ttl_hours: int = 24
    per_ip_per_minute: int = 30
    per_conversation_per_minute: int = 10
    decision_timeout_seconds: float = 8.0
    answer_timeout_seconds: float = 30.0
    rag_timeout_seconds: float = 1.5
    complaint_timeout_seconds: float = 2.0
    service_git_sha: str = "development"
    contract_version: str = "1.0.0"
    service_version: str = "0.1.0"

    @classmethod
    def load(cls, path: str | Path | None = None) -> RuntimeConfig:
        values: dict[str, object] = {}
        if path:
            values.update(json.loads(Path(path).read_text(encoding="utf-8")))
        for item in fields(cls):
            key = f"RUNTIME_{item.name.upper()}"
            if key not in os.environ:
                continue
            raw = os.environ[key]
            default = getattr(cls(), item.name)
            if isinstance(default, bool):
                values[item.name] = raw.lower() in {"1", "true", "yes"}
            elif isinstance(default, int):
                values[item.name] = int(raw)
            elif isinstance(default, float):
                values[item.name] = float(raw)
            else:
                values[item.name] = raw
        return cls(**values)
