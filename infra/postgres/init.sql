CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS runtime;
CREATE SCHEMA IF NOT EXISTS audit;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_reader_app') THEN CREATE ROLE rag_reader_app LOGIN PASSWORD 'local-rag-reader'; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_ingestor_app') THEN CREATE ROLE rag_ingestor_app LOGIN PASSWORD 'local-rag-writer'; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'runtime_app') THEN CREATE ROLE runtime_app LOGIN PASSWORD 'local-runtime'; END IF;
END $$;
GRANT USAGE ON SCHEMA runtime, audit TO runtime_app;
