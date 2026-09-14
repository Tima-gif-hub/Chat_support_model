from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatRequest:
    messages: tuple[dict[str, str], ...]
    max_new_tokens: int
    seed: int | None = None
    temperature: float = 0.7
    top_k: int = 20
    top_p: float = 0.8
    min_p: float = 0.0
    repetition_penalty: float = 1.0
    stop_sequences: tuple[str, ...] = ("<|im_end|>",)
    enable_thinking: bool = False

    @classmethod
    def from_openai(
        cls,
        value: dict[str, Any],
        default_max_tokens: int,
        *,
        default_temperature: float = 0.7,
        default_top_k: int = 20,
        default_top_p: float = 0.8,
        default_min_p: float = 0.0,
    ) -> ChatRequest:
        messages = value.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty array")
        clean: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {
                "system",
                "user",
                "assistant",
                "tool",
            }:
                raise ValueError("invalid message role")
            if not isinstance(message.get("content"), str):
                raise ValueError("message content must be text")
            clean.append({"role": message["role"], "content": message["content"]})
        max_tokens = value.get("max_tokens", default_max_tokens)
        if (
            isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or not 1 <= max_tokens <= default_max_tokens
        ):
            raise ValueError("max_tokens is outside the supported range")
        seed = value.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError("seed must be an integer")
        temperature = value.get("temperature", default_temperature)
        top_k = value.get("top_k", default_top_k)
        top_p = value.get("top_p", default_top_p)
        min_p = value.get("min_p", default_min_p)
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, int | float)
            or not math.isfinite(float(temperature))
            or not 0 <= float(temperature) <= 2
        ):
            raise ValueError("temperature is outside the supported range")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k is outside the supported range")
        if (
            isinstance(top_p, bool)
            or not isinstance(top_p, int | float)
            or not math.isfinite(float(top_p))
            or not 0 < float(top_p) <= 1
        ):
            raise ValueError("top_p is outside the supported range")
        if (
            isinstance(min_p, bool)
            or not isinstance(min_p, int | float)
            or not math.isfinite(float(min_p))
            or not 0 <= float(min_p) <= 1
        ):
            raise ValueError("min_p is outside the supported range")
        return cls(
            tuple(clean),
            max_tokens,
            seed,
            float(temperature),
            top_k,
            float(top_p),
            float(min_p),
        )
