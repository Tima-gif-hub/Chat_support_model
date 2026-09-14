from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

from .errors import RateLimitError

RESTRICTED = re.compile(
    r"(?:reveal|show|print|ignore|leak|give me).{0,50}"
    r"(?:system prompt|hidden prompt|developer message|secret|api key|other customer|internal id)",
    re.IGNORECASE | re.DOTALL,
)
INJECTION = re.compile(
    r"(?:ignore (?:all |the )?(?:previous|above) instructions|"
    r"treat (?:the )?(?:document|evidence) as instructions|developer mode)",
    re.IGNORECASE,
)


def restricted_request(message: str) -> bool:
    return bool(RESTRICTED.search(message) or INJECTION.search(message))


class SlidingWindowRateLimiter:
    """Thread-safe local fallback. Rejects when accounting itself fails."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.monotonic()
        try:
            with self._lock:
                bucket = self._events[key]
                while bucket and bucket[0] <= now - window_seconds:
                    bucket.popleft()
                if len(bucket) >= limit:
                    raise RateLimitError("request rate limit exceeded")
                bucket.append(now)
        except RateLimitError:
            raise
        except Exception as exc:
            raise RateLimitError("rate limit accounting unavailable") from exc


class RedisRateLimiter:
    """Redis-backed counters with a local failover.

    Redis is deliberately not authoritative: a restart may lose counters but
    can never lose conversations or complaints.  If Redis is unavailable we
    continue with the process-local limiter; if that limiter cannot account,
    it fails closed through ``RateLimitError``.
    """

    def __init__(self, url: str, fallback: SlidingWindowRateLimiter | None = None):
        self.fallback = fallback or SlidingWindowRateLimiter()
        self.client: Any | None = None
        try:
            import redis

            self.client = redis.Redis.from_url(
                url, socket_connect_timeout=0.2, socket_timeout=0.2, decode_responses=True
            )
        except (ImportError, ValueError):
            # The dependency-light test/runtime path has no Redis client.  It
            # still gets correct bounded local accounting.
            self.client = None

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if self.client is not None:
            try:
                bucket = f"support:rate:{key}:{int(time.time()) // window_seconds}"
                pipe = self.client.pipeline(transaction=True)
                pipe.incr(bucket)
                pipe.expire(bucket, window_seconds + 1)
                count, _ = pipe.execute()
                if int(count) > limit:
                    raise RateLimitError("request rate limit exceeded")
                return
            except RateLimitError:
                raise
            except Exception:
                # Redis is ephemeral; local accounting preserves the safety
                # boundary during a transient cache outage.
                pass
        self.fallback.check(key, limit, window_seconds)

    def ready(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self.client.ping())
        except Exception:
            return False
