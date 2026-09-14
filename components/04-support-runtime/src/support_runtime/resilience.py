from __future__ import annotations

import random
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TypeVar

from .errors import DependencyUnavailable

T = TypeVar("T")


class CircuitBreaker:
    def __init__(
        self, failure_threshold: int = 5, window_seconds: float = 30, open_seconds: float = 30
    ):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.open_seconds = open_seconds
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if time.monotonic() - self._opened_at >= self.open_seconds:
                return "half_open"
            return "open"

    def call(self, operation: Callable[[], T]) -> T:
        if self.state == "open":
            raise DependencyUnavailable("dependency circuit is open")
        try:
            result = operation()
        except Exception:
            self._record_failure()
            raise
        with self._lock:
            self._failures.clear()
            self._opened_at = None
        return result

    def _record_failure(self) -> None:
        now = time.monotonic()
        with self._lock:
            while self._failures and self._failures[0] < now - self.window_seconds:
                self._failures.popleft()
            self._failures.append(now)
            if len(self._failures) >= self.failure_threshold:
                self._opened_at = now


def retry(operation: Callable[[], T], attempts: int, jitter: tuple[float, float] = (0, 0)) -> T:
    last: Exception | None = None
    for number in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last = exc
            if number + 1 < attempts:
                time.sleep(random.uniform(*jitter))
    assert last is not None
    raise last
