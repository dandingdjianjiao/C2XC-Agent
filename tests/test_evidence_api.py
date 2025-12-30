from __future__ import annotations

import os
import tempfile
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.storage.sqlite_store import SQLiteStore


def _seed_run_with_kb_query_events(*, db_path: str) -> str:
    store = SQLiteStore(db_path)
    try:
        batch = store.create_batch(
            user_request="test",
            n_runs=1,
            recipes_per_run=1,
            config={"dry_run": True},
        )
        run = store.create_run(batch_id=batch.batch_id, run_index=1)

        store.append_event(
            run.run_id,
            "kb_query",
            {
                "ts": 0,
                "agent": "orchestrator",
                "kb_namespace": "kb_principles",
                "query": "q",
                "mode": "mix",
                "top_k": 2,
                "results": [
                    {
                        "alias": "C1",
                        "ref": "kb:kb_principles__chunk-1",
                        "source": "paper1.pdf",
                        "content": "chunk-1 text",
                        "kb_namespace": "kb_principles",
                        "lightrag_chunk_id": "chunk-1",
                    },
                    {
                        "alias": "C2",
                        "ref": "kb:kb_modulation__chunk-2",
                        "source": "paper2.pdf",
                        "content": "chunk-2 text",
                        "kb_namespace": "kb_modulation",
                        "lightrag_chunk_id": "chunk-2",
                    },
                ],
            },
        )
        return run.run_id
    finally:
        store.close()


def test_evidence_list_aggregates_from_kb_query_events(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        run_id = _seed_run_with_kb_query_events(db_path=db_path)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/runs/{run_id}/evidence")
            assert resp.status_code == 200
            page = resp.json()
            assert page["has_more"] is False
            assert page["next_cursor"] is None
            assert [i["alias"] for i in page["items"]] == ["C1", "C2"]
            assert "content" not in page["items"][0]

            resp_full = client.get(f"/api/v1/runs/{run_id}/evidence?include_content=true")
            assert resp_full.status_code == 200
            page_full = resp_full.json()
            assert page_full["items"][0]["content"] == "chunk-1 text"


def test_evidence_get_by_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        run_id = _seed_run_with_kb_query_events(db_path=db_path)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/runs/{run_id}/evidence/C2")
            assert resp.status_code == 200
            item = resp.json()
            assert item["alias"] == "C2"
            assert item["content"] == "chunk-2 text"

            resp2 = client.get(f"/api/v1/runs/{run_id}/evidence/{quote('[C1]')}")
            assert resp2.status_code == 200
            item2 = resp2.json()
            assert item2["alias"] == "C1"


def test_evidence_pagination_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        run_id = _seed_run_with_kb_query_events(db_path=db_path)

        app = create_app()
        with TestClient(app) as client:
            resp1 = client.get(f"/api/v1/runs/{run_id}/evidence?limit=1")
            assert resp1.status_code == 200
            page1 = resp1.json()
            assert [i["alias"] for i in page1["items"]] == ["C1"]
            assert page1["has_more"] is True
            assert page1["next_cursor"]

            resp2 = client.get(
                f"/api/v1/runs/{run_id}/evidence?limit=1&cursor={quote(page1['next_cursor'])}"
            )
            assert resp2.status_code == 200
            page2 = resp2.json()
            assert [i["alias"] for i in page2["items"]] == ["C2"]
            assert page2["has_more"] is False


def test_evidence_run_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("C2XC_SQLITE_PATH", os.path.join(td, "app.db"))
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/runs/run_missing/evidence")
            assert resp.status_code == 404
            payload = resp.json()
            assert payload["error"]["code"] == "not_found"
