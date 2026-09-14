FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
RUN pip install --no-cache-dir "fastapi==0.115.14" "uvicorn==0.34.3" "psycopg[binary]==3.2.9" "redis==5.2.1"
COPY src /app/src
COPY configs /app/configs
COPY migrations /app/migrations
RUN mkdir -p /data && chown -R 65532:65532 /app /data

USER 65532:65532
EXPOSE 8000
ENV RUNTIME_CONFIG=/app/configs/runtime.json RUNTIME_SQLITE_PATH=/data/runtime.db
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"
CMD ["python", "-m", "support_runtime"]
