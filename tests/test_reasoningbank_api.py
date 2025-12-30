from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.runtime.worker import RunWorker
from src.storage.sqlite_store import SQLiteStore


def _create_dry_run_batch_and_run(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/batches",
        json={
            "user_request": "test",
            "n_runs": 1,
            "recipes_per_run": 1,
            "temperature": 0.1,
            "dry_run": True,
        },
    )
    assert resp.status_code == 200, resp.text
    runs = resp.json().get("runs") or []
    assert runs and runs[0].get("run_id")
    return str(runs[0]["run_id"])


def _create_product(client: TestClient, name: str) -> str:
    resp = client.post("/api/v1/products", json={"name": name, "status": "active"})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["product"]["product_id"])


def test_memories_api_crud(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        chroma_dir = os.path.join(td, "chroma")

        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_RB_CHROMA_DIR", chroma_dir)
        monkeypatch.setenv("C2XC_RB_EMBEDDING_MODE", "hash")
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        app = create_app()
        with TestClient(app) as client:
            bad = client.post(
                "/api/v1/memories",
                json={"role": "global", "type": "reasoningbank_item", "content": "nope"},
            )
            assert bad.status_code == 400

            created = client.post(
                "/api/v1/memories",
                json={
                    "role": "global",
                    "status": "active",
                    "type": "manual_note",
                    "content": "My manual note about Cu-Ag synergy.",
                    "schema_version": 1,
                    "extra": {"tags": ["manual"]},
                },
            )
            assert created.status_code == 200, created.text
            mem = created.json()["memory"]
            mem_id = str(mem["mem_id"])
            assert mem["status"] == "active"
            assert mem["type"] == "manual_note"

            got = client.get(f"/api/v1/memories/{mem_id}")
            assert got.status_code == 200
            assert got.json()["memory"]["mem_id"] == mem_id

            patched = client.patch(
                f"/api/v1/memories/{mem_id}",
                json={"content": "Updated note: Cu-Ag can improve C2H4 selectivity."},
            )
            assert patched.status_code == 200, patched.text
            assert "Updated note" in patched.json()["memory"]["content"]

            browse = client.get("/api/v1/memories?limit=50")
            assert browse.status_code == 200
            ids = [str(i["mem_id"]) for i in (browse.json().get("items") or [])]
            assert mem_id in ids

            search = client.get("/api/v1/memories?query=Cu-Ag&limit=10")
            assert search.status_code == 200
            ids2 = [str(i["mem_id"]) for i in (search.json().get("items") or [])]
            assert mem_id in ids2

            archived = client.post(f"/api/v1/memories/{mem_id}/archive", json={"reason": "test"})
            assert archived.status_code == 200, archived.text
            assert archived.json()["memory"]["status"] == "archived"


def test_feedback_upsert_enqueues_rb_job_and_worker_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        chroma_dir = os.path.join(td, "chroma")

        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_RB_CHROMA_DIR", chroma_dir)
        monkeypatch.setenv("C2XC_RB_EMBEDDING_MODE", "hash")
        monkeypatch.setenv("C2XC_RB_LEARN_DRY_RUN", "1")
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        app = create_app()
        with TestClient(app) as client:
            run_id = _create_dry_run_batch_and_run(client)
            p1 = _create_product(client, "C2H4")
            p2 = _create_product(client, "CO")

            put = client.put(
                f"/api/v1/runs/{run_id}/feedback",
                json={
                    "score": 7.0,
                    "pros": "good",
                    "cons": "",
                    "other": "",
                    "products": [
                        {"product_id": p1, "value": 2.0},
                        {"product_id": p2, "value": 1.0},
                    ],
                },
            )
            assert put.status_code == 200, put.text

        store = SQLiteStore(db_path)
        try:
            job = store.get_latest_rb_job_for_run(run_id=run_id, kind="learn")
            assert job is not None
            assert str(job["status"]) in {"queued", "running", "completed"}

            # Execute the job synchronously (single-worker mode).
            worker = RunWorker(db_path=db_path)
            claimed = store.claim_next_queued_rb_job()
            assert claimed is not None
            worker._execute_rb_job(store, claimed)  # type: ignore[attr-defined]

            deltas = store.list_rb_deltas_for_run(run_id=run_id)
            assert deltas
            latest = deltas[0]
            assert str(latest["status"]) == "applied"
            assert len(latest.get("ops") or []) >= 1

        finally:
            store.close()

        # Now the RB memories API should surface learned items.
        with TestClient(app) as client2:
            items = client2.get("/api/v1/memories?status=active&limit=50")
            assert items.status_code == 200, items.text
            assert len(items.json().get("items") or []) >= 1

            # Rollback the latest applied delta and verify active memories drop to zero.
            rolled = client2.post(f"/api/v1/runs/{run_id}/reasoningbank/rollback", json={})
            assert rolled.status_code == 200, rolled.text

            after = client2.get("/api/v1/memories?status=active&limit=50")
            assert after.status_code == 200, after.text
            assert len(after.json().get("items") or []) == 0

