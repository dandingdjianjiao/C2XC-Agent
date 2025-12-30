from __future__ import annotations

import os
from dataclasses import dataclass

from .lightrag_kb import LightRAGKnowledgeBase, build_lightrag_instance


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@dataclass(frozen=True)
class KnowledgeBases:
    """Two semantic LightRAG KB instances (principles vs modulation)."""

    kb_principles: LightRAGKnowledgeBase
    kb_modulation: LightRAGKnowledgeBase

    @classmethod
    def from_env(cls) -> "KnowledgeBases":
        principles_dir = _require_env("LIGHTRAG_KB_PRINCIPLES_DIR")
        modulation_dir = _require_env("LIGHTRAG_KB_MODULATION_DIR")

        principles_rag = build_lightrag_instance(
            working_dir=principles_dir,
            workspace="kb_principles",
            chunk_size=512,
        )
        modulation_rag = build_lightrag_instance(
            working_dir=modulation_dir,
            workspace="kb_modulation",
            chunk_size=512,
        )

        return cls(
            kb_principles=LightRAGKnowledgeBase(
                kb_namespace="kb_principles", rag=principles_rag
            ),
            kb_modulation=LightRAGKnowledgeBase(
                kb_namespace="kb_modulation", rag=modulation_rag
            ),
        )

