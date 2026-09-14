from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class FixedWindowRateLimiter:
    """A bounded, thread-safe fixed-window limiter for one API process."""

    def __init__(self, requests: int, window_seconds: int, max_keys: int) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        with self._lock:
            for active_key, (started, _) in list(self._windows.items()):
                if current >= started + self.window_seconds:
                    del self._windows[active_key]
            window = self._windows.get(key)
            if window is None:
                if len(self._windows) >= self.max_keys:
                    next_available = min(
                        started + self.window_seconds for started, _ in self._windows.values()
                    )
                    retry_after = max(1, math.ceil(next_available - current))
                    return RateLimitDecision(False, retry_after)
                self._windows[key] = (current, 1)
                return RateLimitDecision(True)
            started, count = window
            if count >= self.requests:
                retry_after = max(1, math.ceil(started + self.window_seconds - current))
                return RateLimitDecision(False, retry_after)
            self._windows[key] = (started, count + 1)
            return RateLimitDecision(True)
