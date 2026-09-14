# Support runtime profile

The runtime composes model decisions, retrieval evidence, citations, complaint consent, persistence, and client-safe failure handling behind the public chat contract. Its state-changing paths are owned by the runtime boundary.

## Configuration

Conversation limits, dependency timeouts, and request budgets are recorded in [`configs/runtime.json`](../configs/runtime.json). Runtime security controls include bounded input and history, server-side citation checks, explicit complaint consent, idempotent writes, and append-only audit events.

> Illustrative values for the report layout; not production measurements.

| Metric | Value |
| --- | ---: |
| Decision latency, p95 | 1.3 s |
| End-to-end time to first token (TTFT), p95 | 2.2 s |
| Full response latency, p95 | 7.1 s |
| Complaint persistence latency, p95 | 780 ms |

Decision latency is the p95 time to classify and route a request. End-to-end TTFT is the p95 time from the runtime request to the first answer token, including the serving boundary. Full response latency covers the completed answer path. Complaint persistence latency covers the confirmed write path.

The browser clients that present this workflow are [customer chat](../../../apps/customer-chat/README.md) and [manager console](../../../apps/manager-console/README.md).
