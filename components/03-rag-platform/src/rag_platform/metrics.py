"""Small dependency-free Prometheus instrumentation for the RAG service."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager


class RagMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: defaultdict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {
            "rag_reranker_threshold": 0.35,
            "rag_fused_candidates": 0,
        }
        self._duration_sum = 0.0
        self._duration_count = 0
        self._duration_buckets = {
            bound: 0
            for bound in (0.05, 0.1, 0.25, 0.5, 0.8, 1.0, 2.0, float("inf"))
        }

    @contextmanager
    def retrieval_timer(self) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - started
            with self._lock:
                self._duration_sum += elapsed
                self._duration_count += 1
                for bound in self._duration_buckets:
                    if elapsed <= bound:
                        self._duration_buckets[bound] += 1

    def retrieval(
        self,
        *,
        status: str,
        dense_candidates: int,
        lexical_candidates: int,
        fused_candidates: int | None = None,
    ) -> None:
        """Record one retrieval using the actual candidate-set cardinalities.

        ``dense_candidates`` and ``lexical_candidates`` are the rows returned
        by each search, not merely configured limits.  This distinction is
        important for diagnosing sparse indexes and makes the fused counter
        equal to the union that was actually reranked.
        """
        if fused_candidates is None:
            fused_candidates = max(dense_candidates, lexical_candidates)
        with self._lock:
            self._counters["rag_retrieval_requests_total"] += 1
            self._counters[f"rag_retrieval_status_total{{status=\"{status}\"}}"] += 1
            self._counters["rag_dense_candidates_total"] += dense_candidates
            self._counters["rag_lexical_candidates_total"] += lexical_candidates
            self._counters["rag_fused_candidates_total"] += fused_candidates
            self._gauges["rag_fused_candidates"] = fused_candidates
            if status == "insufficient_evidence":
                self._counters["rag_insufficient_evidence_total"] += 1

    def failure(self) -> None:
        with self._lock:
            self._counters["rag_retrieval_failures_total"] += 1

    def index(self, version: str, status: str = "active") -> None:
        # Label values are controlled by the index manifest, not query input.
        with self._lock:
            self._gauges[f"rag_index_info{{index_version=\"{version}\",status=\"{status}\"}}"] = 1

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP rag_retrieval_duration_seconds Retrieval latency.",
                "# TYPE rag_retrieval_duration_seconds histogram",
                f"rag_retrieval_duration_seconds_sum {self._duration_sum:.9f}",
                f"rag_retrieval_duration_seconds_count {self._duration_count}",
            ]
            for bound, count in self._duration_buckets.items():
                label = "+Inf" if bound == float("inf") else f"{bound:g}"
                lines.append(f'rag_retrieval_duration_seconds_bucket{{le="{label}"}} {count}')
            for name, value in sorted(self._counters.items()):
                lines.append(f"{name} {value:g}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"{name} {value:g}")
            lines.extend(
                [
                    "# HELP rag_retrieval_circuit_state "
                    "Dependency circuit state (0=closed,1=open).",
                    "# TYPE rag_retrieval_circuit_state gauge",
                    "rag_retrieval_circuit_state 0",
                ]
            )
            return "\n".join(lines) + "\n"
