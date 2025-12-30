from __future__ import annotations

import os
import tempfile

import pytest

from src.api.errors import APIError
from src.api.routers.batches import CreateBatchRequest, create_batch


def test_idempotency_same_key_same_body_returns_same_batch_id(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("C2XC_SQLITE_PATH", os.path.join(td, "app.db"))

        body = CreateBatchRequest(user_request="test", n_runs=1, recipes_per_run=1, dry_run=True)
        r1 = create_batch(body, idempotency_key="k1")
        r2 = create_batch(body, idempotency_key="k1")
        assert r1["batch"]["batch_id"] == r2["batch"]["batch_id"]


def test_idempotency_same_key_different_body_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("C2XC_SQLITE_PATH", os.path.join(td, "app.db"))

        b1 = CreateBatchRequest(user_request="test", n_runs=1, recipes_per_run=1, dry_run=True)
        b2 = CreateBatchRequest(user_request="different", n_runs=1, recipes_per_run=1, dry_run=True)

        _ = create_batch(b1, idempotency_key="k1")
        with pytest.raises(APIError) as e:
            _ = create_batch(b2, idempotency_key="k1")
        assert e.value.status_code == 409
        assert e.value.code == "conflict"

