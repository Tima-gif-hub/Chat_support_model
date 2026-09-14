FROM python:3.11-slim
WORKDIR /app
COPY src /app/src
COPY fixtures /app/fixtures
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
ENTRYPOINT ["python", "-m", "model_preparation.cli"]
CMD ["validate-fixture", "/app/fixtures/synthetic-training.jsonl"]
