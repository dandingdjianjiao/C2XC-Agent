from __future__ import annotations

import json
import sqlite3
import tempfile

from src.storage.sqlite_store import SQLiteStore


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1;",
        (name,),
    ).fetchone()
    return row is not None


def test_reconcile_running_runs_marks_failed_and_records_event() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = f"{td}/app.db"
        store = SQLiteStore(db_path)
        try:
            batch = store.create_batch(
                user_request="test",
                n_runs=1,
                recipes_per_run=1,
                config={"dry_run": True},
            )
            run = store.create_run(batch_id=batch.batch_id, run_index=1)
            store.update_run_status(run.run_id, "running")

            reconciled = store.reconcile_running_runs(reason="server_restarted")
            assert reconciled == 1

            run_row = store.get_run(run_id=run.run_id)
            assert run_row is not None
            assert run_row["status"] == "failed"
            assert run_row["error"] == "server_restarted"

            evt = store.get_latest_event(run_id=run.run_id, event_type="run_failed")
            assert evt is not None
            payload = json.loads(evt["payload_json"])
            assert payload["error"] == "server_restarted"
        finally:
            store.close()


def test_migration_creates_idempotency_table() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = f"{td}/app.db"
        store = SQLiteStore(db_path)
        try:
            assert _table_exists(store._conn, "idempotency_keys")
        finally:
            store.close()

