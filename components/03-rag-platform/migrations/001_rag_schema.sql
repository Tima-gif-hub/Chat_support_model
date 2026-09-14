CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.index_versions (
    index_version text PRIMARY KEY,
    workspace_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('inactive', 'active')),
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz,
    CHECK ((status = 'active') = (activated_at IS NOT NULL))
);

-- An index is never made active by an INSERT.  The lifecycle function below
-- is the sole promotion path and verifies the manifest quality gate.
CREATE OR REPLACE FUNCTION rag.require_approved_manifest() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'active' AND current_setting('rag.lifecycle_operation', true) IS DISTINCT FROM 'activate' THEN
        RAISE EXCEPTION 'index activation must use rag.activate_index';
    END IF;
    IF NEW.status = 'active' AND COALESCE(NEW.manifest->>'quality_gate', '') <> 'passed' THEN
        RAISE EXCEPTION 'only indexes with quality_gate=passed may be active';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'active' AND NEW.status <> 'active' THEN
        -- Deactivation is performed only by rag.activate_index, under its
        -- transaction lock.  This trigger cannot identify the caller, so the
        -- function remains the documented writer boundary.
        NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS rag_manifest_gate ON rag.index_versions;
CREATE TRIGGER rag_manifest_gate
    BEFORE INSERT OR UPDATE ON rag.index_versions
    FOR EACH ROW EXECUTE FUNCTION rag.require_approved_manifest();

CREATE UNIQUE INDEX IF NOT EXISTS one_active_rag_index_per_workspace
    ON rag.index_versions (workspace_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS rag.documents (
    index_version text NOT NULL REFERENCES rag.index_versions(index_version) ON DELETE CASCADE,
    document_id text NOT NULL,
    workspace_id text NOT NULL,
    title text NOT NULL,
    document_type text NOT NULL,
    source_uri text NOT NULL,
    language text NOT NULL,
    audience text NOT NULL,
    effective_from timestamptz,
    effective_to timestamptz,
    updated_at timestamptz NOT NULL,
    content_sha256 char(64) NOT NULL,
    PRIMARY KEY (index_version, document_id),
    CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_from < effective_to)
);

CREATE TABLE IF NOT EXISTS rag.chunks (
    index_version text NOT NULL,
    document_id text NOT NULL,
    chunk_id text NOT NULL,
    heading_path text[] NOT NULL DEFAULT '{}',
    content text NOT NULL,
    token_start integer NOT NULL,
    token_end integer NOT NULL,
    content_sha256 char(64) NOT NULL,
    workspace_id text NOT NULL,
    audience text NOT NULL,
    language text NOT NULL,
    effective_from timestamptz,
    effective_to timestamptz,
    updated_at timestamptz NOT NULL,
    source_uri text NOT NULL,
    embedding vector(768) NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    PRIMARY KEY (index_version, chunk_id),
    FOREIGN KEY (index_version, document_id)
        REFERENCES rag.documents(index_version, document_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw
    ON rag.chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Retrieval transactions set this locally before dense search.  Keeping the
-- value here documents the production query contract without changing the
-- server-wide PostgreSQL setting.
CREATE INDEX IF NOT EXISTS rag_chunks_search_gin ON rag.chunks USING gin (search_vector);
CREATE INDEX IF NOT EXISTS rag_chunks_acl_validity
    ON rag.chunks (workspace_id, audience, language, effective_from, effective_to);

CREATE OR REPLACE FUNCTION rag.activate_index(target_version text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE target_workspace text;
BEGIN
    PERFORM set_config('rag.lifecycle_operation', 'activate', true);
    SELECT workspace_id INTO STRICT target_workspace
    FROM rag.index_versions WHERE index_version = target_version FOR UPDATE;
    UPDATE rag.index_versions SET status = 'inactive', activated_at = NULL
      WHERE workspace_id = target_workspace AND status = 'active';
    UPDATE rag.index_versions SET status = 'active', activated_at = now()
      WHERE index_version = target_version;
END;
$$;
ALTER FUNCTION rag.activate_index(text) SET search_path = rag, pg_temp;
