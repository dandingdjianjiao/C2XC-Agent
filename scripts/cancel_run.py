#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.storage.sqlite_store import SQLiteStore  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Request cancellation for a running/queued run (SQLite-backed).")
    p.add_argument("--run-id", required=True, help="Run id to cancel (e.g. run_<uuid>).")
    p.add_argument("--db-path", default="", help="SQLite path (default: env C2XC_SQLITE_PATH or data/app.db).")
    p.add_argument("--reason", default="user_cancel", help="Optional reason to record.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    store = SQLiteStore(args.db_path or None)
    try:
        cancel_id = store.request_cancel(target_type="run", target_id=str(args.run_id), reason=str(args.reason))
        print(cancel_id)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

