from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.recap.engine import RecapEngine, RecapError

from .types import AgentContext


@dataclass(frozen=True)
class OrchestratorResult:
    recipes_json: dict[str, Any]
    citations: dict[str, str]  # alias -> canonical kb ref (from final output)
    memory_ids: list[str]  # mem_id list cited in final output (mem:<id>)


class OrchestratorAgent:
    name = "orchestrator"

    def __init__(self) -> None:
        self._engine = RecapEngine()

    def run(self, ctx: AgentContext, user_request: str) -> OrchestratorResult:
        try:
            recipes_json, citations, memory_ids = self._engine.run(ctx, user_request=user_request)
        except RecapError:
            raise
        except Exception as e:
            raise RecapError(str(e)) from e

        return OrchestratorResult(recipes_json=recipes_json, citations=citations, memory_ids=memory_ids)
