from __future__ import annotations

import json
import os
import tempfile

import pytest

from src.runtime.worker import RunWorker
from src.storage.sqlite_store import SQLiteStore


def test_dry_run_writes_synthetic_evidence_and_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)

        store = SQLiteStore(db_path)
        try:
            batch = store.create_batch(
                user_request="test",
                n_runs=1,
                recipes_per_run=1,
                config={"dry_run": True, "temperature": 0.7},
            )
            run = store.create_run(batch_id=batch.batch_id, run_index=1)

            worker = RunWorker(db_path=db_path)
            # Private, but deterministic and fast: we only validate the dry-run branch.
            worker._execute_one(store, run_id=run.run_id, batch_id=batch.batch_id)  # type: ignore[attr-defined]

            out_row = store.get_latest_event(run_id=run.run_id, event_type="final_output")
            assert out_row is not None
            payload = json.loads(str(out_row["payload_json"]))

            citations = payload.get("citations") or {}
            assert isinstance(citations, dict)
            assert citations, "dry-run should include synthetic citations for UI parity"

            evidence_page = store.list_evidence_page(
                run_id=run.run_id,
                limit=200,
                cursor=None,
                include_content=True,
            )
            evidence_aliases = {str(i.get("alias") or "") for i in evidence_page.get("items", [])}
            assert evidence_aliases, "dry-run should record kb_query events so evidence is available"

            # Evidence shown to the user should correspond exactly to cited aliases.
            assert evidence_aliases == set(citations.keys())

            # The output text should actually contain inline citations like [C1].
            recipes_json = payload.get("recipes_json") or {}
            text = json.dumps(recipes_json, ensure_ascii=False)
            for alias in citations.keys():
                assert f"[{alias}]" in text
        finally:
            store.close()

