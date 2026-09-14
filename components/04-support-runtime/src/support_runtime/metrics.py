from __future__ import annotations

import threading
from collections import defaultdict


class RuntimeMetrics:
    """Small dependency-free Prometheus registry for runtime health signals."""

    _complaint_outcomes = ("confirmation_required", "submitted", "failed")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = 0
        self._complaints: defaultdict[str, int] = defaultdict(int)
        self._citation_failures = 0

    def readiness(self, value: bool) -> None:
        with self._lock:
            self._ready = int(value)

    def complaint(self, outcome: str) -> None:
        if outcome not in self._complaint_outcomes:
            raise ValueError(f"unsupported complaint outcome: {outcome}")
        with self._lock:
            self._complaints[outcome] += 1

    def citation_failure(self) -> None:
        with self._lock:
            self._citation_failures += 1

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# TYPE support_runtime_ready gauge",
                f"support_runtime_ready {self._ready}",
                "# TYPE support_runtime_complaints_total counter",
            ]
            lines.extend(
                f'support_runtime_complaints_total{{outcome="{outcome}"}} '
                f"{self._complaints[outcome]}"
                for outcome in self._complaint_outcomes
            )
            lines.extend(
                [
                    "# TYPE support_runtime_citation_failures_total counter",
                    f"support_runtime_citation_failures_total {self._citation_failures}",
                ]
            )
            return "\n".join(lines) + "\n"
