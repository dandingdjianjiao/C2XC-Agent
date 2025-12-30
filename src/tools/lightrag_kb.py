from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal, TYPE_CHECKING

from .kb_citations import make_kb_ref


QueryMode = Literal["local", "global", "hybrid", "naive", "mix", "bypass"]

if TYPE_CHECKING:
    from lightrag.lightrag import LightRAG


@dataclass(frozen=True)
class KBChunk:
    ref: str  # canonical: "kb:<kb_namespace>__<lightrag_chunk_id>"
    content: str
    source: str  # DOI or filename/path (no page number)
    kb_namespace: str
    lightrag_chunk_id: str | None = None  # LightRAG internal chunk id (e.g. "chunk-<md5>")


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def _get_env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def build_lightrag_instance(
    *,
    working_dir: str,
    workspace: str,
    chunk_size: int = 512,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    embedding_model: str | None = None,
    embedding_base_url: str | None = None,
    embedding_api_key: str | None = None,
    embedding_dim: int | None = None,
    embedding_send_dimensions: bool | None = None,
) -> LightRAG:
    """Create a LightRAG instance (HKU LightRAG) using OpenAI-compatible endpoints.

    Notes:
    - LightRAG uses its own storage in `working_dir` (local default: NanoVectorDB + NetworkX + JsonKV).
    - `chunk_size` is enforced as token chunking size (spec: 512).
    """
    # Imported lazily so that:
    # - `--dry-run` can work without LightRAG installed
    # - runtime container can decide the dependency set
    from lightrag.lightrag import LightRAG
    from lightrag.llm.openai import openai_complete, openai_embed
    from lightrag.utils import EmbeddingFunc

    resolved_llm_model = llm_model or _get_env("LLM_MODEL", _get_env("OPENAI_MODEL", "gpt-4o-mini"))  # type: ignore[arg-type]
    resolved_llm_base_url = llm_base_url or _get_env("OPENAI_API_BASE", _get_env("OPENAI_BASE_URL", "https://api.openai.com/v1"))  # type: ignore[arg-type]
    resolved_llm_api_key = llm_api_key or _get_env("OPENAI_API_KEY", "")

    resolved_embedding_model = embedding_model or _get_env(
        "C2XC_EMBEDDING_MODEL",
        _get_env("EMBEDDING_MODEL", "text-embedding-3-small"),
    )
    resolved_embedding_base_url = embedding_base_url or _get_env(
        "C2XC_EMBEDDING_API_BASE",
        _get_env("EMBEDDING_API_BASE", resolved_llm_base_url),  # type: ignore[arg-type]
    )
    resolved_embedding_api_key = embedding_api_key or _get_env(
        "C2XC_EMBEDDING_API_KEY",
        _get_env("EMBEDDING_API_KEY", resolved_llm_api_key),
    )
    resolved_embedding_dim = embedding_dim or int(_get_env("C2XC_EMBEDDING_DIM", _get_env("EMBEDDING_DIM", "1536")))  # type: ignore[arg-type]
    resolved_embedding_send_dimensions = (
        embedding_send_dimensions
        if embedding_send_dimensions is not None
        else _get_env_bool("EMBEDDING_SEND_DIMENSIONS", False)
    )
    if embedding_send_dimensions is None:
        resolved_embedding_send_dimensions = _get_env_bool(
            "C2XC_EMBEDDING_SEND_DIMENSIONS",
            resolved_embedding_send_dimensions,
        )

    # NOTE: Do NOT partial-bind `openai_complete_if_cache` directly: it's decorated by tenacity,
    # so the wrapper accepts `*args, **kwargs` and will treat the first positional arg as `model`,
    # causing `got multiple values for argument 'model'` when LightRAG calls it as (prompt, ...).
    # `openai_complete` is the prompt-first wrapper LightRAG expects; it reads `llm_model_name`
    # from `hashing_kv.global_config` (i.e. LightRAG's global_config).
    llm_model_func = partial(
        openai_complete,
        base_url=resolved_llm_base_url,
        api_key=resolved_llm_api_key,
    )

    # `openai_embed` is an EmbeddingFunc instance. Use `.func` (unwrapped) to avoid nesting.
    embedding_func = EmbeddingFunc(
        embedding_dim=resolved_embedding_dim,
        func=partial(
            openai_embed.func,
            model=resolved_embedding_model,
            base_url=resolved_embedding_base_url,
            api_key=resolved_embedding_api_key,
        ),
        # Opt-in only: many OpenAI-compatible endpoints don't support the "dimensions" parameter.
        # Qwen (e.g. text-embedding-v4) does; set EMBEDDING_SEND_DIMENSIONS=1 to enable.
        send_dimensions=resolved_embedding_send_dimensions,
        model_name=resolved_embedding_model,
    )

    return LightRAG(
        working_dir=working_dir,
        workspace=workspace,
        chunk_token_size=chunk_size,
        embedding_func=embedding_func,
        llm_model_func=llm_model_func,
        llm_model_name=resolved_llm_model,
    )


@dataclass
class LightRAGKnowledgeBase:
    """Thin wrapper that exposes KB search with chunk-level citations."""

    kb_namespace: str
    rag: Any

    def query_chunks(
        self,
        query: str,
        *,
        mode: QueryMode = "mix",
        top_k: int = 10,
        chunk_top_k: int | None = None,
    ) -> list[KBChunk]:
        from lightrag.base import QueryParam
        from lightrag.utils import always_get_an_event_loop

        chunk_top_k = chunk_top_k if chunk_top_k is not None else top_k
        always_get_an_event_loop().run_until_complete(self.rag.initialize_storages())
        data = self.rag.query_data(
            query,
            param=QueryParam(mode=mode, top_k=top_k, chunk_top_k=chunk_top_k),
        )

        raw_chunks = (data.get("data") or {}).get("chunks") or []
        results: list[KBChunk] = []
        for c in raw_chunks:
            content = (c.get("content") or "").strip()
            if not content:
                continue
            source = (c.get("file_path") or "unknown_source").strip()
            lightrag_chunk_id = (c.get("chunk_id") or "").strip() or None
            if lightrag_chunk_id is None:
                # Extremely defensive: LightRAG should always return chunk_id.
                # If it doesn't, skip rather than producing an unverifiable citation.
                continue
            results.append(
                KBChunk(
                    ref=make_kb_ref(self.kb_namespace, lightrag_chunk_id),
                    content=content,
                    source=source,
                    kb_namespace=self.kb_namespace,
                    lightrag_chunk_id=lightrag_chunk_id,
                )
            )
        return results
