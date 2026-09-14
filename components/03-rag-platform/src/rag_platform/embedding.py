from __future__ import annotations

import hashlib
import math
import re

_WORDS = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokenize(text: str) -> list[str]:
    return _WORDS.findall(text.casefold())


class DeterministicEmbedding:
    """Offline 768-D feature-hash adapter used only by the public demo.

    Production uses separately pinned BGE weights. Naming this adapter explicitly prevents a
    local synthetic retrieval result from being mistaken for a BGE measurement.
    """

    model_name = "deterministic-feature-hash-768"
    revision = "local-v1"

    def __init__(self, dimensions: int = 768, max_tokens: int = 512) -> None:
        if dimensions <= 0 or max_tokens <= 0:
            raise ValueError("embedding dimensions and max_tokens must be positive")
        self.dimensions = dimensions
        self.max_tokens = max_tokens

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        tokens = tokenize(text)[: self.max_tokens]
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[slot] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return tuple(value / norm for value in vector)


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, right, strict=False))
