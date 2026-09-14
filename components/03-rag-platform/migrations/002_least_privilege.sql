DO $$ BEGIN
    CREATE ROLE rag_migrator NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE ROLE rag_ingestor NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE ROLE rag_reader NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

REVOKE ALL ON SCHEMA rag FROM PUBLIC;
GRANT USAGE ON SCHEMA rag TO rag_ingestor, rag_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON rag.documents, rag.chunks TO rag_ingestor;
GRANT SELECT, INSERT ON rag.index_versions TO rag_ingestor;
-- Index status is changed only by the SECURITY DEFINER activation function;
-- ingestors may update manifest metadata but cannot bypass lifecycle gates.
GRANT UPDATE (manifest) ON rag.index_versions TO rag_ingestor;
GRANT SELECT ON rag.index_versions, rag.documents, rag.chunks TO rag_reader;
GRANT EXECUTE ON FUNCTION rag.activate_index(text) TO rag_ingestor;
GRANT rag_ingestor TO rag_ingestor_app;
GRANT rag_reader TO rag_reader_app;
