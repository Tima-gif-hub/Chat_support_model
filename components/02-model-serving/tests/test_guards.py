from __future__ import annotations

import unittest

from model_serving.config import InferenceConfig
from model_serving.service import ModelService


class FixedProvider:
    name = "fixed"

    def __init__(self, output: str) -> None:
        self.output = output

    def load(self) -> None:
        pass

    def complete(self, request: object) -> str:
        return self.output


class GuardTests(unittest.TestCase):
    def test_empty_output_fails_probe(self) -> None:
        service = ModelService(FixedProvider(""), InferenceConfig())
        service.start()
        self.assertEqual(503, service.ready()[1])

    def test_repetition_blocks_request(self) -> None:
        provider = FixedProvider("ready")
        service = ModelService(provider, InferenceConfig())
        service.start()
        provider.output = "again " * 20
        with self.assertRaisesRegex(RuntimeError, "repetition"):
            service.complete({"messages": [{"role": "user", "content": "test"}]})

    def test_malformed_structured_decision_fails(self) -> None:
        provider = FixedProvider("ready")
        service = ModelService(provider, InferenceConfig())
        service.start()
        provider.output = '{"class":"catalog"}'
        with self.assertRaisesRegex(RuntimeError, "structured"):
            service.complete({"messages": [{"role": "user", "content": "test"}]})


if __name__ == "__main__":
    unittest.main()
