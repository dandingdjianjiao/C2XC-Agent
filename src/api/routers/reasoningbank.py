from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_reasoningbank_store
from src.api.errors import APIError
from src.runtime.reasoningbank_jobs import enqueue_rb_learn_job, rollback_rb_delta
from src.storage.reasoningbank_store import ReasoningBankStore
from src.storage.sqlite_store import SQLiteStore


router = APIRouter()


class RollbackRequest(BaseModel):
    delta_id: str | None = Field(default=None)
    reason: str | None = Field(default=None)


@router.post("/runs/{run_id}/reasoningbank/learn")
def learn_reasoningbank(run_id: str) -> dict[str, Any]:
    # Validate run + feedback existence before enqueuing.
    store = SQLiteStore()
    try:
        if store.get_run(run_id=run_id) is None:
            raise APIError(status_code=404, code="not_found", message="Run not found.")
        if store.get_feedback_for_run(run_id=run_id) is None:
            raise APIError(
                status_code=409,
                code="conflict",
                message="Feedback is required before ReasoningBank learning.",
            )

        job = enqueue_rb_learn_job(store, run_id=run_id)
        return {"run_id": run_id, "job_id": job.rb_job_id, "status": job.status}
    finally:
        store.close()


@router.get("/runs/{run_id}/reasoningbank/deltas")
def list_reasoningbank_deltas(run_id: str) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        if store.get_run(run_id=run_id) is None:
            raise APIError(status_code=404, code="not_found", message="Run not found.")
        return {"run_id": run_id, "deltas": store.list_rb_deltas_for_run(run_id=run_id)}
    finally:
        store.close()


@router.get("/runs/{run_id}/reasoningbank/jobs")
def list_reasoningbank_jobs(
    run_id: str,
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        if store.get_run(run_id=run_id) is None:
            raise APIError(status_code=404, code="not_found", message="Run not found.")
        return {"run_id": run_id, "jobs": store.list_rb_jobs_for_run(run_id=run_id, limit=int(limit))}
    finally:
        store.close()


@router.post("/runs/{run_id}/reasoningbank/rollback")
def rollback_reasoningbank(
    run_id: str,
    body: RollbackRequest | None = None,
    rb: ReasoningBankStore = Depends(get_reasoningbank_store),
) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        if store.get_run(run_id=run_id) is None:
            raise APIError(status_code=404, code="not_found", message="Run not found.")

        delta_id = (body.delta_id if body else None) if body is not None else None
        reason = (body.reason if body else None) if body is not None else None

        rolled = rollback_rb_delta(store, rb=rb, run_id=run_id, delta_id=delta_id, reason=reason)
        return {"run_id": run_id, "delta_id": rolled, "status": "rolled_back"}
    finally:
        store.close()
