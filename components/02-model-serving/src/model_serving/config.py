from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InferenceConfig:
    enable_thinking: bool = False
    temperature: float = 0.7
    top_k: int = 20
    top_p: float = 0.8
    min_p: float = 0.0
    max_new_tokens: int = 1024
    repetition_penalty: float = 1.0
    stop_sequences: tuple[str, ...] = ("<|im_end|>",)
    prompt_token_limit: int = 7168
    reserved_completion_tokens: int = 1024
    request_timeout_seconds: int = 30
    max_concurrent_requests_per_replica: int = 16
    rate_limit_requests_per_window: int = 60
    rate_limit_window_seconds: int = 60
    rate_limit_max_keys: int = 10_000

    @classmethod
    def load(cls, path: Path) -> InferenceConfig:
        raw = path.read_text(encoding="utf-8")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            # The checked-in .yaml files are JSON-compatible YAML.  Keep the
            # parser dependency-free but provide a useful failure for actual
            # YAML rather than silently using defaults.
            raise ValueError(f"inference config must be JSON-compatible YAML: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("inference config must be an object")
        stop_sequences = value.get("stop_sequences", cls.stop_sequences)
        if isinstance(stop_sequences, str) or not isinstance(stop_sequences, list | tuple):
            raise ValueError("stop_sequences must be an array of strings")
        value["stop_sequences"] = tuple(stop_sequences)
        config = cls(**value)
        if not isinstance(config.enable_thinking, bool) or config.enable_thinking:
            raise ValueError("thinking mode must remain disabled")
        numeric = (
            config.temperature,
            config.top_p,
            config.min_p,
            config.repetition_penalty,
        )
        if any(isinstance(item, bool) or not isinstance(item, int | float) for item in numeric):
            raise ValueError("invalid sampling configuration")
        if any(not math.isfinite(float(item)) for item in numeric):
            raise ValueError("invalid sampling configuration")
        if config.prompt_token_limit + config.reserved_completion_tokens != 8192:
            raise ValueError("prompt and completion budgets must total 8192")
        if (
            not 0 <= config.temperature <= 2
            or isinstance(config.top_k, bool)
            or not isinstance(config.top_k, int)
            or config.top_k < 1
            or not 0 < config.top_p <= 1
        ):
            raise ValueError("invalid sampling configuration")
        if not 0 <= config.min_p <= 1 or config.repetition_penalty <= 0:
            raise ValueError("invalid sampling configuration")
        if not config.stop_sequences or any(
            not isinstance(item, str) or not item for item in config.stop_sequences
        ):
            raise ValueError("at least one non-empty stop sequence is required")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (
                config.request_timeout_seconds,
                config.max_concurrent_requests_per_replica,
                config.rate_limit_requests_per_window,
                config.rate_limit_window_seconds,
                config.rate_limit_max_keys,
            )
        ):
            raise ValueError("request limits must be positive integers")
        return config
