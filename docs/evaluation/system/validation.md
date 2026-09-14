# Public implementation validation

The dated results below describe repository checks and synthetic fixture behavior. The public implementation uses synthetic data and a deterministic model simulator, so these results establish contract and integration behavior without establishing production model quality, production retrieval quality, business impact, or service-level attainment. Historical business observations remain in the [case study](../../case-study/production-outcomes.md).

## Validation runs

| Scope | Command or workflow | Result |
|---|---|---|
| Python tests | `python -m pytest -q` | 63 passed |
| Lint | `ruff` | Passed |
| Type checks | Four component `mypy` checks | Passed |
| Customer frontend | Node smoke + Playwright UI | 1 smoke test, 4 Playwright checks |
| Manager frontend | `PLAYWRIGHT_CHANNEL=chrome npm run test:ui` | 1 smoke test, 3 Playwright checks |
| Contract coverage | `scripts/verify_contracts.py` | 3 OpenAPI specs, 5 JSON Schemas, and 300 cases checked |
| Public synthetic evaluation | Full 300-case deterministic suite | Recall@10 0.9333, MRR@10 0.8806 |
| Container build and startup | Docker Compose core services | 7 core images built; stack healthy |
| Strict assembled smoke | `docker compose run --rm smoke` | Passed |
| Production evaluation gate | `scripts/evaluate.py --require-production-provider` | Not evaluated without a real provider |
| Live browser journey | Docker Compose rebuilt apps + browser flow | Passed: grounded cited answer, insufficient evidence, complaint confirmation, complaint submission, and authenticated manager queue |
| Model-serving API | Model-serving test suite | 13 passed, including endpoint `429`/`Retry-After` and provider-bypass checks |
| Lint and hygiene | `python -m ruff check .` and `python scripts/hygiene.py` | Passed |
| Contract verification | `python scripts/verify_contracts.py` and `npm run contract:test` | Passed; 3 OpenAPI specs, 5 JSON Schemas, and 300 cases checked |

The synthetic retrieval result measures fixture relevance; decision and runtime cases measure contract coverage. The local retrieval path uses deterministic hash embeddings, the public provider simulates inference, and browser output demonstrates the event contract with synthetic data. These constraints keep repository evidence separate from the historical production observations in the [case study](../../case-study/public-implementation.md).
