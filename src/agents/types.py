from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.load_config import AppConfig
from src.llm.openai_compat import OpenAICompatibleChatClient
from src.storage.reasoningbank_store import ReasoningBankStore
from src.storage.sqlite_store import SQLiteStore
from src.tools.kb_registry import KnowledgeBases
from src.utils.cancel import CancelledError, CancellationToken


@dataclass
class AgentContext:
    store: SQLiteStore
    config: AppConfig
    kbs: KnowledgeBases | None
    rb: ReasoningBankStore | None
    llm: OpenAICompatibleChatClient | None
    cancel: CancellationToken
    batch_id: str
    run_id: str
    recipes_per_run: int
    temperature: float

    def trace(self, event_type: str, payload: dict[str, Any]) -> None:
        self.store.append_event(self.run_id, event_type, payload)

    def check_cancelled(self) -> None:
        """Check both in-memory and DB-backed cancellation flags."""
        if self.cancel.cancelled:
            raise CancelledError("Cancelled")
        if self.store.is_cancel_requested(target_type="batch", target_id=self.batch_id):
            self.cancel.request_cancel()
            self.store.acknowledge_cancel(target_type="batch", target_id=self.batch_id)
            raise CancelledError("Cancelled")
        if self.store.is_cancel_requested(target_type="run", target_id=self.run_id):
            self.cancel.request_cancel()
            self.store.acknowledge_cancel(target_type="run", target_id=self.run_id)
            raise CancelledError("Cancelled")
