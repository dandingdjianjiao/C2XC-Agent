from __future__ import annotations

import re
from dataclasses import dataclass

from .lightrag_kb import KBChunk


# Alias tokens look like: [C1], [C12], [KB3] ...
# Prefix is one-or-more uppercase letters; suffix is one-or-more digits.
_ALIAS_TOKEN_RE = re.compile(r"\[(?P<alias>[A-Z]+\d+)\]")
_MEM_TOKEN_RE = re.compile(
    r"\bmem:(?P<mem_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)


@dataclass(frozen=True)
class AliasedKBChunk:
    """KB chunk with a short alias for LLM-friendly citation.

    Example:
        alias="C1"
        ref="kb:kb_modulation__chunk-<md5>"
    """

    alias: str
    ref: str
    source: str
    content: str
    kb_namespace: str
    lightrag_chunk_id: str | None


def alias_kb_chunks(
    chunks: list[KBChunk], *, prefix: str = "C"
) -> tuple[list[AliasedKBChunk], dict[str, str]]:
    """Assign stable-in-order aliases [C1], [C2]... for a batch of retrieved chunks.

    Returns:
      - aliased list (same order as input)
      - alias_map: alias -> canonical ref (kb:...)
    """
    aliased: list[AliasedKBChunk] = []
    alias_map: dict[str, str] = {}

    for idx, ch in enumerate(chunks, start=1):
        alias = f"{prefix}{idx}"
        aliased_chunk = AliasedKBChunk(
            alias=alias,
            ref=ch.ref,
            source=ch.source,
            content=ch.content,
            kb_namespace=ch.kb_namespace,
            lightrag_chunk_id=ch.lightrag_chunk_id,
        )
        aliased.append(aliased_chunk)
        alias_map[alias] = ch.ref

    return aliased, alias_map


def extract_citation_aliases(text: str) -> list[str]:
    """Extract alias tokens like [C1] from LLM output.

    Returns aliases in first-seen order, de-duplicated.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _ALIAS_TOKEN_RE.finditer(text):
        alias = m.group("alias")
        if alias in seen:
            continue
        seen.add(alias)
        ordered.append(alias)
    return ordered


def extract_memory_ids(text: str) -> list[str]:
    """Extract memory citations like `mem:<uuid>` from text.

    Returns mem_ids in first-seen order, de-duplicated.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _MEM_TOKEN_RE.finditer(text or ""):
        mem_id = m.group("mem_id")
        if mem_id in seen:
            continue
        seen.add(mem_id)
        ordered.append(mem_id)
    return ordered


def resolve_aliases(
    aliases: list[str], alias_map: dict[str, str]
) -> dict[str, str]:
    """Resolve a list of aliases into canonical refs.

    Raises KeyError if any alias is unknown (program-level validation).
    """
    return {a: alias_map[a] for a in aliases}
