FROM python:3.11-slim
WORKDIR /workspace
COPY . .
ENV PYTHONPATH=/workspace/packages/python-contracts:/workspace/components/01-model-preparation/src:/workspace/components/02-model-serving/src:/workspace/components/03-rag-platform/src:/workspace/components/04-support-runtime/src
CMD ["python", "scripts/system_smoke.py"]
