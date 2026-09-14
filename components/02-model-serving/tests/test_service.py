from __future__ import annotations

import json
import unittest

from model_serving.config import InferenceConfig
from model_serving.providers import DeterministicMockProvider
from model_serving.service import ModelService


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ModelService(
            DeterministicMockProvider(), InferenceConfig(), git_sha="abc1234"
        )

    def test_readiness_requires_start_and_probe(self) -> None:
        self.assertEqual(503, self.service.ready()[1])
        self.service.start()
        self.assertEqual(200, self.service.ready()[1])
        self.assertEqual("abc1234", self.service.version()["git_sha"])

    def test_mock_is_deterministic_and_varied(self) -> None:
        self.service.start()
        delivery = self.service.complete(
            {"messages": [{"role": "user", "content": "What is delivery?"}], "seed": 42}
        )
        repeated = self.service.complete(
            {"messages": [{"role": "user", "content": "What is delivery?"}], "seed": 42}
        )
        complaint = self.service.complete(
            {"messages": [{"role": "user", "content": "My chair is damaged"}]}
        )
        first = json.loads(delivery["choices"][0]["message"]["content"])
        second = json.loads(repeated["choices"][0]["message"]["content"])
        other = json.loads(complaint["choices"][0]["message"]["content"])
        self.assertEqual(first, second)
        self.assertEqual("rag_answer", first["expected_action"])
        self.assertEqual("complaint_tool", other["expected_action"])
        self.assertEqual(
            {
                "complaint_text",
                "category",
                "complaint_type",
                "customer_context",
                "submission_mode",
                "consent_evidence",
            },
            set(other["complaint"]),
        )

    def test_delivery_delay_and_explicit_consent_are_classified(self) -> None:
        self.service.start()
        result = self.service.complete(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "My delivery is five days late and this is frustrating. "
                            "Please submit this complaint."
                        ),
                    }
                ]
            }
        )
        decision = json.loads(result["choices"][0]["message"]["content"])
        self.assertEqual("delivery_delay", decision["complaint"]["complaint_type"])
        self.assertEqual("explicit_request", decision["complaint"]["submission_mode"])
        self.assertIsNotNone(decision["complaint"]["consent_evidence"])

    def test_max_tokens_maps_to_internal_limit(self) -> None:
        self.service.start()
        with self.assertRaisesRegex(ValueError, "max_tokens"):
            self.service.complete(
                {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 1025}
            )


if __name__ == "__main__":
    unittest.main()
