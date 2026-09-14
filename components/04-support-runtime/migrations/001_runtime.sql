BEGIN;

CREATE SCHEMA IF NOT EXISTS runtime;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS runtime.conversations (
    id text PRIMARY KEY,
    workspace_id text NOT NULL,
    customer_id text,
    summary text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.messages (
    id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES runtime.conversations(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    content text NOT NULL,
    request_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conversation_created_idx
    ON runtime.messages (conversation_id, created_at, id);

CREATE TABLE IF NOT EXISTS runtime.complaint_drafts (
    id text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES runtime.conversations(id) ON DELETE CASCADE,
    payload jsonb NOT NULL,
    state text NOT NULL CHECK (state IN ('draft', 'awaiting_confirmation', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime.complaints (
    id text PRIMARY KEY,
    workspace_id text NOT NULL,
    conversation_id text NOT NULL REFERENCES runtime.conversations(id),
    customer_id text,
    complaint_text text NOT NULL CHECK (char_length(complaint_text) BETWEEN 20 AND 4000),
    category text NOT NULL CHECK (category = 'complaint'),
    complaint_type text NOT NULL CHECK (complaint_type IN (
        'waiting_time', 'product_quality', 'price', 'delivery_delay', 'delivery_damage',
        'wrong_item', 'missing_item_or_part', 'payment_issue', 'return_or_refund',
        'service_quality', 'staff_interaction', 'availability_or_stock', 'other'
    )),
    customer_context text NOT NULL DEFAULT '' CHECK (char_length(customer_context) <= 2000),
    consent_source text NOT NULL CHECK (consent_source IN ('explicit_request', 'confirmed')),
    idempotency_key text NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('queued', 'acknowledged', 'resolved', 'failed')),
    internal_notes text NOT NULL DEFAULT '',
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS complaints_open_created_idx
    ON runtime.complaints (created_at)
    WHERE status IN ('queued', 'acknowledged');

CREATE TABLE IF NOT EXISTS runtime.complaint_outbox (
    id text PRIMARY KEY,
    complaint_id text NOT NULL REFERENCES runtime.complaints(id),
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
CREATE INDEX IF NOT EXISTS complaint_outbox_pending_idx
    ON runtime.complaint_outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS runtime.feedback (
    id text PRIMARY KEY,
    message_id text NOT NULL UNIQUE REFERENCES runtime.messages(id),
    rating smallint NOT NULL CHECK (rating IN (-1, 1)),
    comment text NOT NULL DEFAULT '' CHECK (char_length(comment) <= 1000),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime.events (
    conversation_id text NOT NULL REFERENCES runtime.conversations(id) ON DELETE CASCADE,
    sequence bigint NOT NULL,
    request_id text NOT NULL,
    event text NOT NULL,
    data jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, sequence)
);

CREATE TABLE IF NOT EXISTS audit.events (
    id text PRIMARY KEY,
    event_type text NOT NULL,
    actor_type text NOT NULL,
    actor_id text,
    aggregate_id text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_events_aggregate_idx
    ON audit.events (aggregate_id, created_at, id);

CREATE OR REPLACE FUNCTION audit.reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit.events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS audit_events_append_only ON audit.events;
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit.events
FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

-- The migration owner is the local bootstrap role.  Runtime itself connects
-- with the least-privilege runtime_app role in the default Compose stack.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA runtime TO runtime_app;
GRANT SELECT, INSERT ON audit.events TO runtime_app;
GRANT USAGE ON SCHEMA runtime, audit TO runtime_app;

COMMIT;
