from __future__ import annotations

import os
from pathlib import Path

from .config import InferenceConfig
from .manifest import load_manifest
from .providers import create_provider
from .service import ModelService

try:
    from fastapi import FastAPI, HTTPException, Request
except ImportError as exc:  # pragma: no cover - exercised by the container/runtime profile
    raise RuntimeError("Install the 'server' optional dependencies to run the HTTP API") from exc

default_config_path = Path(__file__).resolve().parents[2] / "configs" / "inference.yaml"
config_path = Path(os.getenv("MODEL_CONFIG_PATH", str(default_config_path)))
config = InferenceConfig.load(config_path) if config_path.exists() else InferenceConfig()
provider_name = os.getenv("MODEL_PROVIDER", "mock")
provider = create_provider(
    provider_name,
    endpoint=os.getenv("MODEL_ENDPOINT"),
    model=os.getenv("MODEL_NAME", "Qwen/Qwen3-4B"),
    timeout_seconds=config.request_timeout_seconds,
)
manifest = None
manifest_path = os.getenv("MODEL_MANIFEST_PATH")
if provider_name != "mock":
    if not manifest_path:
        raise RuntimeError("MODEL_MANIFEST_PATH is required for non-mock providers")
    manifest = load_manifest(Path(manifest_path))
service = ModelService(
    provider,
    config,
    git_sha=os.getenv("GIT_SHA", "development"),
    model_version=os.getenv("MODEL_VERSION", manifest["model_version"] if manifest else "mock-1.0"),
    manifest=manifest,
)
service.start()
app = FastAPI(title="Model serving", version="1.0.0")


@app.get("/health/live")
def live() -> dict[str, str]:
    return service.live()


@app.get("/health/ready")
def ready() -> dict[str, object]:
    body, status = service.ready()
    if status != 200:
        raise HTTPException(status_code=status, detail=body)
    return body


@app.get("/version")
def version() -> dict[str, str]:
    return service.version()


@app.post("/v1/chat/completions")
def completion(payload: dict[str, object], request: Request) -> dict[str, object]:
    # Use only the transport peer. Caller-controlled headers cannot bypass a quota.
    client_key = request.client.host if request.client else "unknown"
    decision = service.check_rate_limit(client_key)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="request rate limit exceeded",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    try:
        return service.complete(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/metrics")
def metrics() -> object:
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(service.metrics.prometheus(), media_type="text/plain; version=0.0.4")
