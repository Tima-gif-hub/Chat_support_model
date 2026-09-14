import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_serving.config import InferenceConfig
from model_serving.rate_limit import FixedWindowRateLimiter
from model_serving.service import ModelService


class CountingProvider:
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def load(self) -> None:
        pass

    def complete(self, request: object) -> str:
        self.calls += 1
        return "ready"


class RateLimitTests(unittest.TestCase):
    def test_window_recovers_without_sleeping_in_test(self) -> None:
        limiter = FixedWindowRateLimiter(1, 10, 2)
        self.assertTrue(limiter.check("client", now=100).allowed)
        denied = limiter.check("client", now=101)
        self.assertFalse(denied.allowed)
        self.assertEqual(9, denied.retry_after_seconds)
        self.assertTrue(limiter.check("client", now=110).allowed)

    def test_denied_request_does_not_call_provider(self) -> None:
        provider = CountingProvider()
        config = InferenceConfig(rate_limit_requests_per_window=1)
        service = ModelService(provider, config)
        service.start()
        self.assertEqual(1, provider.calls)  # readiness probe
        payload = {"messages": [{"role": "user", "content": "test"}]}
        self.assertTrue(service.check_rate_limit("client").allowed)
        service.complete(payload)
        self.assertFalse(service.check_rate_limit("client").allowed)
        self.assertEqual(2, provider.calls)

    def test_new_keys_are_rejected_until_capacity_frees(self) -> None:
        limiter = FixedWindowRateLimiter(1, 60, 2)
        limiter.check("a", now=1)
        limiter.check("b", now=1)
        denied = limiter.check("c", now=2)
        self.assertFalse(denied.allowed)
        self.assertEqual(59, denied.retry_after_seconds)
        self.assertTrue(limiter.check("c", now=61).allowed)

    def test_invalid_rate_limit_configuration_is_rejected(self) -> None:
        for field, value in (("rate_limit_requests_per_window", True), ("rate_limit_max_keys", 0)):
            with self.subTest(field=field):
                payload = {
                    "prompt_token_limit": 7168,
                    "reserved_completion_tokens": 1024,
                    field: value,
                }
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "inference.yaml"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        InferenceConfig.load(path)

    def test_http_endpoint_returns_429_without_trusting_header(self) -> None:
        import model_serving.app as app_module
        from fastapi.testclient import TestClient

        class FakeService:
            def __init__(self) -> None:
                self.limiter = FixedWindowRateLimiter(1, 60, 10)
                self.provider_calls = 0

            def check_rate_limit(self, key: str):
                return self.limiter.check(key)

            def complete(self, payload: object):
                self.provider_calls += 1
                return {"ok": True}

            def live(self):
                return {"status": "live"}

        fake = FakeService()
        with patch.object(app_module, "service", fake):
            client = TestClient(app_module.app)
            payload = {"messages": [{"role": "user", "content": "test"}]}
            with patch("model_serving.rate_limit.time.monotonic", return_value=100.0):
                self.assertEqual(200, client.post("/v1/chat/completions", json=payload).status_code)
                response = client.post(
                    "/v1/chat/completions",
                    json=payload,
                    headers={"X-RateLimit-Key": "different-client"},
                )
            self.assertEqual(429, response.status_code)
            self.assertEqual("60", response.headers["retry-after"])
            self.assertEqual(1, fake.provider_calls)
            self.assertEqual(200, client.get("/health/live").status_code)


if __name__ == "__main__":
    unittest.main()
