# Security and privacy controls

The local demo uses anonymous signed sessions and seeded manager credentials. Production cookies are HTTP-only, Secure, SameSite=Lax, and manager endpoints enforce roles server-side. Customer access is scoped to a conversation; RAG filters are taken from trusted server context.

Messages are bounded at 8,000 characters, rate limited, screened for prompt injection, and validated before routing. Documents are untrusted data, never instructions. Structured logs retain request ID, route, status, latency, versions, token counts, and error class without raw messages. Complaint creation, confirmation, duplicate detection, and status changes append audit events. The threat tests live beside their enforcing component.
