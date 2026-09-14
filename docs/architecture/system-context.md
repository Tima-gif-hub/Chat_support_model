# System context

The customer and manager web apps call only the support runtime through the same-origin gateway.

Runtime owns request validation, decision routing, grounded generation, complaint consent, persistence, audit, and client-facing failure policy. It consumes versioned model and retrieval contracts over HTTP.

RAG owns the active index lifecycle; model serving owns loading and readiness.

PostgreSQL is authoritative for documents, conversations, complaints, audit, and outbox data. Redis is an ephemeral rate/cursor/cache dependency.

The default Compose path swaps in a deterministic provider and synthetic knowledge base. The service boundaries, retrieval, citation checks, complaint transaction, and UI states remain real.

Model preparation contains behavior policy and produces an artifact for serving; changing company facts remain versioned retrieval documents. Serving exposes a versioned provider boundary with readiness and output guards. RAG applies workspace, audience, language, and validity filters before dense and full-text retrieval are fused and reranked. Runtime performs structured routing before grounded generation, enforces citation validity, and owns complaint consent, idempotency, persistence, and audit. Conversation history is bounded to eight recent turns and an approximately 2,400-token summary budget. App, model, and index versions have independent identities so each boundary can be inspected and rolled back separately.
