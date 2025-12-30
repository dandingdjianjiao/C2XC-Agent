#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    host = os.getenv("C2XC_HOST", "127.0.0.1")
    port = int(os.getenv("C2XC_PORT", "8000"))
    reload = os.getenv("C2XC_RELOAD", "1").strip().lower() in {"1", "true", "yes", "y", "on"}

    try:
        import uvicorn  # type: ignore
    except Exception as e:
        print("Missing dependency: uvicorn. Install it in your runtime environment.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 1

    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=os.getenv("C2XC_LOG_LEVEL", "info"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

