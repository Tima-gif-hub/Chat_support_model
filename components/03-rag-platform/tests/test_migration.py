from pathlib import Path


def test_migration_has_vector_fts_hnsw_and_acl_indexes() -> None:
    component = Path(__file__).resolve().parents[1]
    sql = (component / "migrations" / "001_rag_schema.sql").read_text(encoding="utf-8").lower()
    assert "vector(768)" in sql
    assert "using hnsw" in sql
    assert "ef_construction = 64" in sql
    assert "using gin" in sql
    assert "workspace_id, audience, language" in sql
    assert "activate_index" in sql
