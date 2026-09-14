from __future__ import annotations

import threading
from collections import defaultdict


class ServingMetrics:
    """Dependency-free Prometheus registry with owned model metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: defaultdict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {
            "model_serving_ready": 0,
            "model_serving_queue_depth": 0,
            "model_serving_circuit_state": 0,
        }
        self.duration_sum = 0.0
        self.duration_count = 0
        self.ttft_buckets = {
            bound: 0
            for bound in (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float("inf"))
        }

    def ready(self, value: bool) -> None:
        with self._lock:
            self.gauges["model_serving_ready"] = int(value)

    def queue(self, value: int) -> None:
        with self._lock:
            self.gauges["model_serving_queue_depth"] = value

    def inference(
        self, elapsed: float, *, input_tokens: int | None, output_tokens: int | None
    ) -> None:
        with self._lock:
            self.counters["model_serving_requests_total"] += 1
            self.counters["model_serving_input_tokens_total"] += input_tokens or 0
            self.counters["model_serving_output_tokens_total"] += output_tokens or 0
            self.duration_sum += elapsed
            self.duration_count += 1
            for bound in self.ttft_buckets:
                if elapsed <= bound:
                    self.ttft_buckets[bound] += 1

    def guard_failure(self, reason: str) -> None:
        with self._lock:
            self.counters[f'model_serving_guard_failures_total{{reason="{reason}"}}'] += 1
            if reason == "provider_error":
                self.gauges["model_serving_circuit_state"] = 1

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# TYPE model_serving_generation_duration_seconds summary",
                f"model_serving_generation_duration_seconds_sum {self.duration_sum:.9f}",
                f"model_serving_generation_duration_seconds_count {self.duration_count}",
                "# TYPE model_serving_time_to_first_token_seconds histogram",
            ]
            for bound, count in self.ttft_buckets.items():
                label = "+Inf" if bound == float("inf") else f"{bound:g}"
                lines.append(
                    f'model_serving_time_to_first_token_seconds_bucket{{le="{label}"}} {count}'
                )
            lines.extend(f"{name} {value:g}" for name, value in sorted(self.counters.items()))
            lines.extend(f"{name} {value:g}" for name, value in sorted(self.gauges.items()))
            return "\n".join(lines) + "\n"
