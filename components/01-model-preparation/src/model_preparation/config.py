from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QLoRAConfig:
    """Validated JSON/YAML-compatible QLoRA configuration."""

    values: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> QLoRAConfig:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("QLoRA config must be an object")
        if value.get("method") != "qlora_sft" or value.get("seed") != 42:
            raise ValueError("unsupported QLoRA configuration")
        optimization = value.get("optimization", {})
        quantization = value.get("quantization", {})
        if quantization.get("compute_dtype") != "bfloat16":
            raise ValueError("production QLoRA configuration requires BF16")
        expected_batch = optimization.get("micro_batch_size", 1) * optimization.get(
            "gradient_accumulation_steps", 1
        )
        if optimization.get("effective_batch_size_per_replica", expected_batch) != expected_batch:
            raise ValueError("effective batch size does not match accumulation settings")
        return cls(value)
