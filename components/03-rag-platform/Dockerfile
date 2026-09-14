FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "fastapi==0.115.14" "uvicorn==0.34.3" "psycopg[binary]==3.2.9"
COPY src /app/src
COPY fixtures /app/fixtures
COPY configs /app/configs
COPY migrations /app/migrations
ENV PYTHONPATH=/app/src RAG_SOURCE_DIR=/app/fixtures/knowledge-base
USER 65532:65532
EXPOSE 8080
CMD ["uvicorn", "rag_platform.api:app", "--host", "0.0.0.0", "--port", "8080"]
