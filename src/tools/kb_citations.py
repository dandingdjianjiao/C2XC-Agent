from __future__ import annotations


def make_kb_chunk_id(kb_namespace: str, lightrag_chunk_id: str) -> str:
    """Make a stable, namespaced chunk id for citations.

    Project decision:
    - Use LightRAG's own chunk_id (content-hash based, stored inside LightRAG).
    - Add `kb_namespace` prefix to avoid collisions across the two KB instances.

    Result format:
        "<kb_namespace>__<lightrag_chunk_id>"
    """
    kb_namespace = kb_namespace.strip()
    lightrag_chunk_id = lightrag_chunk_id.strip()
    return f"{kb_namespace}__{lightrag_chunk_id}"


def make_kb_ref(kb_namespace: str, lightrag_chunk_id: str) -> str:
    """Return canonical citation reference string: `kb:<chunk_id>`."""
    return f"kb:{make_kb_chunk_id(kb_namespace, lightrag_chunk_id)}"
