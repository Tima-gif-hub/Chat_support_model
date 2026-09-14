# Model serving profile

Serving is the deployment boundary for an approved model artifact. The public implementation keeps provider loading, readiness, request validation, generation controls, and output guards behind the versioned inference contract.

## Configuration

Generation defaults and request budgets are recorded in [`configs/inference.yaml`](../configs/inference.yaml). The serving boundary verifies an approved artifact manifest before a production provider becomes ready.

> Illustrative values for the report layout; not production measurements.

| Metric | Value |
| --- | ---: |
| Time to first token (TTFT), p95 | 0.7 s |

TTFT is the elapsed time from an accepted inference request at the serving boundary to the first generated token. This illustrative serving scenario assumes 10 concurrent sessions with responses up to 300 tokens; generation duration is not represented here.

The next stage is [03 — building the company knowledge layer](../../03-rag-platform/README.md).
