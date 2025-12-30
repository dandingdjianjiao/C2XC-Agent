from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.storage.sqlite_store import SQLiteStore


def _seed_run(*, db_path: str) -> str:
    store = SQLiteStore(db_path)
    try:
        batch = store.create_batch(
            user_request="test",
            n_runs=1,
            recipes_per_run=1,
            config={"dry_run": True},
        )
        run = store.create_run(batch_id=batch.batch_id, run_index=1)
        return run.run_id
    finally:
        store.close()


def _create_product(client: TestClient, name: str) -> str:
    resp = client.post("/api/v1/products", json={"name": name, "status": "active"})
    assert resp.status_code == 200
    return str(resp.json()["product"]["product_id"])


def test_feedback_upsert_computes_and_persists_fractions(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        run_id = _seed_run(db_path=db_path)

        app = create_app()
        with TestClient(app) as client:
            p1 = _create_product(client, "C2H4")
            p2 = _create_product(client, "CO")

            put = client.put(
                f"/api/v1/runs/{run_id}/feedback",
                json={
                    "score": 7.5,
                    "pros": "good",
                    "cons": "",
                    "other": "",
                    "products": [
                        {"product_id": p1, "value": 2.0},
                        {"product_id": p2, "value": 1.0},
                    ],
                },
            )
            assert put.status_code == 200
            fb = put.json()["feedback"]
            assert fb["run_id"] == run_id
            fracs = {r["product_id"]: r["fraction"] for r in fb["products"]}
            assert fracs[p1] == pytest.approx(2.0 / 3.0)
            assert fracs[p2] == pytest.approx(1.0 / 3.0)

            get = client.get(f"/api/v1/runs/{run_id}/feedback")
            assert get.status_code == 200
            fb2 = get.json()["feedback"]
            fracs2 = {r["product_id"]: r["fraction"] for r in fb2["products"]}
            assert fracs2 == fracs


def test_feedback_sum_zero_sets_all_fractions_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        run_id = _seed_run(db_path=db_path)

        app = create_app()
        with TestClient(app) as client:
            p1 = _create_product(client, "C2H4")
            p2 = _create_product(client, "CO")

            put = client.put(
                f"/api/v1/runs/{run_id}/feedback",
                json={
                    "score": None,
                    "pros": "",
                    "cons": "",
                    "other": "",
                    "products": [
                        {"product_id": p1, "value": 0.0},
                        {"product_id": p2, "value": 0.0},
                    ],
                },
            )
            assert put.status_code == 200
            fb = put.json()["feedback"]
            fracs = {r["product_id"]: r["fraction"] for r in fb["products"]}
            assert fracs[p1] == 0.0
            assert fracs[p2] == 0.0


def test_feedback_rejects_duplicate_product_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_ENABLE_WORKER", "0")

        run_id = _seed_run(db_path=db_path)

        app = create_app()
        with TestClient(app) as client:
            p1 = _create_product(client, "C2H4")

            put = client.put(
                f"/api/v1/runs/{run_id}/feedback",
                json={
                    "score": 1,
                    "pros": "",
                    "cons": "",
                    "other": "",
                    "products": [
                        {"product_id": p1, "value": 1.0},
                        {"product_id": p1, "value": 2.0},
                    ],
                },
            )
            assert put.status_code == 400
            payload = put.json()
            assert payload["error"]["code"] == "invalid_argument"

