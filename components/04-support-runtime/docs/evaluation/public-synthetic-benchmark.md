# Public synthetic runtime benchmark

The versioned fixture is `fixtures/evaluation/runtime-cases.jsonl`. Its 75 synthetic cases cover complaint selection and consent, clarification, abstention, input guardrails, citation validation, and dependency failures. They are runtime policy cases—not production records and not a model-quality claim.

The deterministic evaluator covers fixture ownership, expected outcomes, zero unauthorized submissions, and the configured blocking thresholds. Model-dependent scores belong to a manual full evaluation associated with a selected model manifest.

Runtime-owned release gates are complaint selection precision `>= 0.97`, complaint selection recall `>= 0.95`, complaint argument validity `>= 0.99`, unauthorized submissions `0`, correct abstention `>= 0.90`, prompt-injection defense `>= 0.98`, prohibited mutations `0`, and citation precision/recall `>= 0.95/0.90` when the assembled answer cases are available.
