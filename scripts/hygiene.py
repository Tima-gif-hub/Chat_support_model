from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
IGNORED = {".work", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def main() -> int:
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED for part in path.parts):
            continue
        if path.suffix in {".pyc", ".log", ".tmp", ".bak"}:
            offenders.append(str(path.relative_to(ROOT)))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if FORBIDDEN.search(text):
            offenders.append(f"secret-like text: {path.relative_to(ROOT)}")
    if offenders:
        raise SystemExit("hygiene failures:\n" + "\n".join(offenders))
    print("hygiene checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
