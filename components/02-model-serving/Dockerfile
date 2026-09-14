FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.14 uvicorn==0.34.3
COPY src /app/src
COPY configs /app/configs
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "model_serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
