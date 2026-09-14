from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .ingestion import build_index
from .models import RetrievalContext
from .retrieval import HybridRetriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or query the deterministic local RAG index")
    parser.add_argument("source", type=Path)
    parser.add_argument("--index-version", default="idx_local_fixture_v1")
    parser.add_argument("--query")
    args = parser.parse_args()
    documents, chunks = build_index(args.source, args.index_version)
    if args.query:
        response = HybridRetriever(chunks, args.index_version).retrieve(
            args.query,
            RetrievalContext("anonymous-furniture-company", "customer", "en", datetime.now(UTC)),
        )
        print(json.dumps(response.as_dict(), indent=2))
    else:
        print(json.dumps({"documents": len(documents), "chunks": len(chunks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
