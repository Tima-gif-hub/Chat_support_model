# API rate limiting

`POST /v1/chat/completions` has two separate request guards. The existing
`max_concurrent_requests_per_replica` semaphore limits work in flight. The
rate limiter limits accepted request starts per client key, before inference
and before the provider is called.

The default profile allows 60 requests per 60 seconds per socket peer and
tracks at most 10,000 keys in one process. A rejected request receives HTTP `429` and a
`Retry-After` header. The server returns immediately and does not sleep.

These settings are `rate_limit_requests_per_window`,
`rate_limit_window_seconds`, and `rate_limit_max_keys` in
[`inference.yaml`](../configs/inference.yaml). Values are positive integers.
The in-memory fixed-window state is thread-safe and bounded, but it belongs
to one running process. The socket peer may represent a whole proxy or runtime,
so all end users behind that peer share one quota. New peers are rejected while the bounded key table is
full; active keys are never evicted. The current single-worker deployment therefore has a
per-replica quota: multiple workers or replicas have independent windows,
and a restart clears the counters. A shared Redis or gateway limiter is the
appropriate next boundary when one global quota is required; this component
does not claim distributed rate limiting.
