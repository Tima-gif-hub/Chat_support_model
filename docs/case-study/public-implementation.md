# Public implementation case study

I built the customer support assistant represented by this anonymized public implementation for a furniture company. The public tree preserves the system boundaries, model preparation workflow, retrieval design, runtime behavior, evaluation approach, and operational controls. The public edition uses synthetic fixtures and a deterministic local provider.

## Production experience represented

The system was a customer support assistant. It answered company questions from cited knowledge, asked a focused clarification when required information was missing, abstained when evidence was insufficient, and prepared classified complaints for a manager queue. Order changes, payments, inventory changes, delivery scheduling, refunds, and account changes remained outside the assistant boundary.

My work covered four bounded areas: model preparation, model deployment, an independent RAG platform, and API/app integration through support runtime. The web applications are presentation-only clients of the runtime. The repository is a monorepo with explicit process boundaries; the boundaries describe ownership and interfaces rather than a claim that the production deployment was a single process.

## Reported production observations

The following observations were measured approximately six weeks after launch and are kept separate from the public demo:

- Requests handled outside manager working hours increased by 15%.
- Requests closed without manager participation increased from approximately 5% to approximately 36%.
- The company reported an increase in completed sales, but no percentage was disclosed.

These observations are reported outcomes, not a causal experiment or a guarantee. The reported mechanism was immediate initial consultation followed by manager contact for order-specific details. The public repository does not reproduce these business outcomes.

## Public reconstruction

The default Compose path uses synthetic furniture documents, synthetic customer records, and a deterministic model simulator. It exercises the repository's ingestion, retrieval, citation checks, orchestration, complaint persistence, and interface journeys without production credentials, data, or model weights. Results from this path are technical and contract coverage only; they are not production model-quality or business-performance measurements.

Illustrative technical targets are kept separate from measured observations in [measurement context](measurement-context.md). This keeps design choices and synthetic fixture results distinct from production measurements.

See [production business outcomes](production-outcomes.md), the [system evaluation overview](../evaluation/system/README.md), and the [validation record](../evaluation/system/validation.md) for the current evidence boundary.
