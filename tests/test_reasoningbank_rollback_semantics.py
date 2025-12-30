from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

from src.config.load_config import load_app_config
from src.runtime.reasoningbank_jobs import rollback_rb_delta
from src.storage.reasoningbank_store import MemoryItem, ReasoningBankStore
from src.storage.sqlite_store import SQLiteStore


def _memory_to_dict(item: MemoryItem) -> dict[str, Any]:
    return {
        "mem_id": item.mem_id,
        "status": item.status,
        "role": item.role,
        "type": item.type,
        "content": item.content,
        "source_run_id": item.source_run_id,
        "created_at": float(item.created_at),
        "updated_at": float(item.updated_at),
        "schema_version": int(item.schema_version),
        "extra": item.extra,
    }


def test_rb_rollback_update_overrides_manual_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "app.db")
        chroma_dir = os.path.join(td, "chroma")

        monkeypatch.setenv("C2XC_SQLITE_PATH", db_path)
        monkeypatch.setenv("C2XC_RB_CHROMA_DIR", chroma_dir)
        monkeypatch.setenv("C2XC_RB_EMBEDDING_MODE", "hash")

        cfg = load_app_config()
        rb = ReasoningBankStore.from_config(cfg)

        store = SQLiteStore(db_path)
        try:
            batch = store.create_batch(
                user_request="test",
                n_runs=1,
                recipes_per_run=1,
                config={"dry_run": True},
            )
            run = store.create_run(batch_id=batch.batch_id, run_index=1)

            before = rb.upsert(
                mem_id=None,
                status="active",
                role="global",
                type="manual_note",
                content="Before: baseline memory content.",
                source_run_id=None,
                schema_version=1,
                extra={"v": 1},
                preserve_created_at=True,
            )
            after = rb.upsert(
                mem_id=before.mem_id,
                status="active",
                role="global",
                type="manual_note",
                content="After: RB learn updated this memory.",
                source_run_id=None,
                schema_version=1,
                extra={"v": 2},
                preserve_created_at=True,
            )

            delta = store.create_rb_delta(
                run_id=run.run_id,
                ops=[
                    {
                        "op": "update",
                        "mem_id": before.mem_id,
                        "before": _memory_to_dict(before),
                        "after": _memory_to_dict(after),
                    }
                ],
                schema_version=1,
                extra={"test": True},
            )

            # User manually edits after the RB learn update (this must be overwritten by strict rollback).
            rb.upsert(
                mem_id=before.mem_id,
                status="active",
                role="global",
                type="manual_note",
                content="MANUAL EDIT: user changed the content after learn.",
                source_run_id=None,
                schema_version=1,
                extra={"v": 999},
                preserve_created_at=True,
            )

            rolled = rollback_rb_delta(
                store,
                rb=rb,
                run_id=run.run_id,
                delta_id=delta.delta_id,
                reason="test_strict_rollback",
            )
            assert rolled == delta.delta_id

            restored = rb.get(mem_id=before.mem_id)
            assert restored is not None
            assert restored.content == before.content
            assert restored.extra == before.extra
            assert restored.status == before.status

            delta_row = store.get_rb_delta(delta_id=delta.delta_id)
            assert delta_row is not None
            assert str(delta_row["status"]) == "rolled_back"
        finally:
            store.close()

