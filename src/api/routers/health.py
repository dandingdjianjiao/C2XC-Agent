from __future__ import annotations

import importlib.metadata
import time
from typing import Any

from fastapi import APIRouter
from fastapi import Request

from src.storage.sqlite_store import SCHEMA_VERSION
from src.storage.sqlite_store import SQLiteStore


router = APIRouter()


def _pkg_version(name: str) -> str | None:
    try:
        return str(importlib.metadata.version(name))
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def version() -> dict[str, Any]:
    return {
        "service": "c2xc-agent",
        "api": "v1",
        "schema_version": int(SCHEMA_VERSION),
        "deps": {
            "fastapi": _pkg_version("fastapi"),
            "uvicorn": _pkg_version("uvicorn"),
            "chromadb": _pkg_version("chromadb"),
            "openai": _pkg_version("openai"),
        },
        "ts": time.time(),
    }


@router.get("/system/worker")
def system_worker(request: Request) -> dict[str, Any]:
    # Expose minimal runtime observability for WebUI debugging.
    worker = getattr(request.app.state, "run_worker", None)
    worker_snapshot: dict[str, Any] = {"enabled": worker is not None, "running": False}
    if worker is not None and hasattr(worker, "status_snapshot"):
        worker_snapshot.update(worker.status_snapshot())

    store = SQLiteStore()
    try:
        return {
            "ts": time.time(),
            "worker": worker_snapshot,
            "queue": {
                "runs_by_status": store.count_runs_by_status(),
                "batches_by_status": store.count_batches_by_status(),
                "rb_jobs_by_status": store.count_rb_jobs_by_status(),
            },
            "startup": {
                "reconciled_running_runs": getattr(request.app.state, "reconciled_running_runs", 0),
            },
        }
    finally:
        store.close()
