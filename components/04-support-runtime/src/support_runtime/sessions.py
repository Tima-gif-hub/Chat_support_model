"""Signed browser sessions for the two presentation boundaries.

The runtime is the only component that may mint or validate sessions.  The
cookie contains an opaque, random subject and an HMAC signature; it contains
no credentials or conversation contents.  This keeps the local demo
stateless while preserving the production ownership boundary.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

CUSTOMER_COOKIE = "support_customer_session"
MANAGER_COOKIE = "support_manager_session"
_LOCAL_SESSION_SECRET = "local-only-change-me"


def validate_security_configuration() -> None:
    """Reject demo credentials when the process declares production mode."""
    if os.getenv("APP_ENV", "local").lower() != "production":
        return
    secret = os.getenv("SESSION_SECRET", "")
    if not secret or secret == _LOCAL_SESSION_SECRET or len(secret) < 32:
        raise RuntimeError("production requires a unique SESSION_SECRET of at least 32 characters")
    if not os.getenv("MANAGER_EMAIL") or not os.getenv("MANAGER_PASSWORD"):
        raise RuntimeError("production requires MANAGER_EMAIL and MANAGER_PASSWORD")
    if os.getenv("MANAGER_PASSWORD") == "portfolio-manager":
        raise RuntimeError("production must not use the demo manager password")


def _secret() -> bytes:
    # A non-production default makes the CPU-local demo runnable.  Production
    # deployments must inject SESSION_SECRET and set APP_ENV=production.
    value = os.getenv("SESSION_SECRET", _LOCAL_SESSION_SECRET)
    return value.encode("utf-8")


def _encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _decode(value: str | None) -> dict[str, Any] | None:
    if not value or value.count(".") != 1:
        return None
    body, supplied = value.split(".", 1)
    expected = base64.urlsafe_b64encode(
        hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(supplied, expected):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str):
        return None
    if not isinstance(payload.get("exp"), int) or payload["exp"] < int(time.time()):
        return None
    return payload


def new_customer_session() -> tuple[str, str]:
    subject = f"anon_{secrets.token_urlsafe(18)}"
    return subject, _encode({"sub": subject, "kind": "customer", "exp": int(time.time()) + 86400})


def new_manager_session(email: str, role: str = "manager") -> str:
    return _encode(
        {
            "sub": email,
            "kind": "manager",
            "role": role,
            "exp": int(time.time()) + 8 * 3600,
        }
    )


def customer_from_cookie(value: str | None) -> str | None:
    payload = _decode(value)
    if payload is None or payload.get("kind") != "customer":
        return None
    return str(payload["sub"])


def manager_from_cookie(value: str | None) -> dict[str, str] | None:
    payload = _decode(value)
    if payload is None or payload.get("kind") != "manager":
        return None
    role = payload.get("role")
    if role not in {"manager", "admin"}:
        return None
    return {"email": str(payload["sub"]), "role": str(role)}


def cookie_options() -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": os.getenv("APP_ENV", "local").lower() == "production",
        "samesite": "lax",
        "path": "/",
    }
