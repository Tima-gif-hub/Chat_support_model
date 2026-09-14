from __future__ import annotations

import os


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install server dependencies before starting the runtime") from exc
    uvicorn.run(
        "support_runtime.api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
