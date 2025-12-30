from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from src.storage.sqlite_store import SQLiteStore


def _now_ts() -> float:
    return time.time()


@dataclass(frozen=True)
class DryRunEvidenceChunk:
    alias: str
    ref: str
    source: str
    content: str
    kb_namespace: str
    lightrag_chunk_id: str | None


def _synthetic_chunks(*, alias_prefix: str, count: int) -> list[DryRunEvidenceChunk]:
    n = int(count)
    if n < 1:
        n = 1

    # Keep this deliberately explicit: dry-run is for UI/trace pipeline testing,
    # not for scientific validity.
    templates: list[dict[str, str]] = [
        {
            "kb_namespace": "kb_principles",
            "title": "Synthetic principle chunk",
            "content": (
                "DRY RUN — synthetic evidence chunk.\n"
                "Purpose: validate Evidence UI + citation linking.\n"
                "\n"
                "Claim stub: This chunk is not real literature and must not be used for science.\n"
            ),
        },
        {
            "kb_namespace": "kb_modulation",
            "title": "Synthetic modulation chunk",
            "content": (
                "DRY RUN — synthetic evidence chunk.\n"
                "Purpose: validate Evidence UI + citation linking.\n"
                "\n"
                "Claim stub: This chunk is not real literature and must not be used for science.\n"
            ),
        },
        {
            "kb_namespace": "kb_principles",
            "title": "Synthetic extra chunk",
            "content": (
                "DRY RUN — synthetic evidence chunk.\n"
                "Purpose: validate multi-citation behavior.\n"
                "\n"
                "Note: content intentionally short.\n"
            ),
        },
    ]

    chunks: list[DryRunEvidenceChunk] = []
    for i in range(n):
        alias = f"{alias_prefix}{i + 1}"
        tpl = templates[i % len(templates)]
        kb_namespace = tpl["kb_namespace"]
        ref = f"kb:dry_run/{kb_namespace}/synthetic_{i+1}"
        source = f"DRY_RUN::{tpl['title']}::{i+1}"
        content = tpl["content"].strip()
        chunks.append(
            DryRunEvidenceChunk(
                alias=alias,
                ref=ref,
                source=source,
                content=content,
                kb_namespace=kb_namespace,
                lightrag_chunk_id=f"dry_run_chunk_{i+1}",
            )
        )

    return chunks


def _build_placeholder_output(
    *,
    recipes_per_run: int,
    evidence: list[DryRunEvidenceChunk],
) -> tuple[dict[str, Any], dict[str, str]]:
    n = int(recipes_per_run)
    if n < 1:
        n = 1

    if not evidence:
        # Extremely defensive: should not happen.
        evidence = _synthetic_chunks(alias_prefix="C", count=1)

    # Ensure every evidence alias is cited at least once across the output,
    # while still keeping recipe count exact.
    aliases = [c.alias for c in evidence]
    citations = {c.alias: c.ref for c in evidence}

    combos: list[tuple[str, str]] = [("Cu", "Mo"), ("Ni", "Fe"), ("Ag", "Cu")]
    ratios: list[str] = ["1:1", "2:1", "1:2"]

    recipes: list[dict[str, Any]] = []
    for i in range(n):
        m1, m2 = combos[i % len(combos)]
        ratio = ratios[i % len(ratios)]

        if n == 1:
            cite = " ".join(f"[{a}]" for a in aliases)
        else:
            cite = f"[{aliases[i % len(aliases)]}]"

        recipes.append(
            {
                "M1": m1,
                "M2": m2,
                "atomic_ratio": ratio,
                "small_molecule_modifier": "benzoic acid (-COOH)",
                "rationale": (
                    "DRY RUN PLACEHOLDER — synthetic output for UI pipeline testing. "
                    f"No KB/LLM calls were made. {cite}"
                ),
            }
        )

    recipes_json: dict[str, Any] = {
        "recipes": recipes,
        "overall_notes": "DRY RUN PLACEHOLDER — synthetic run for testing only.",
    }
    return recipes_json, citations


def append_dry_run_simulation(
    store: SQLiteStore,
    *,
    run_id: str,
    user_request: str,
    recipes_per_run: int,
    temperature: float,
    run_index: int,
    n_runs: int,
    alias_prefix: str = "C",
) -> tuple[dict[str, Any], dict[str, str]]:
    """Append a synthetic, deterministic-ish trace for dry-run.

    Goal: dry-run should exercise the same UI surfaces as normal runs:
    - Output contains citations ([C1], …) + citations map
    - Evidence endpoint can aggregate from kb_query events
    - Trace shows representative event types for filtering
    """
    alias_count = max(2, int(recipes_per_run))
    evidence_chunks = _synthetic_chunks(alias_prefix=alias_prefix, count=alias_count)

    store.append_event(
        run_id,
        "recap_info",
        {
            "ts": _now_ts(),
            "agent": "orchestrator",
            "recap_state": "dry_run",
            "task_name": "dry_run_simulation",
            "think": "DRY RUN: synthetic trace (no LLM/KB calls).",
            "subtasks": [
                {
                    "type": "kb_search",
                    "kb_name": "kb_principles",
                    "query": "DRY RUN synthetic query",
                    "top_k": len(evidence_chunks),
                    "mode": "mix",
                },
                {"type": "generate_recipes"},
            ],
            "result": "",
            "depth": 0,
            "steps": 1,
        },
    )

    store.append_event(
        run_id,
        "llm_request",
        {
            "ts": _now_ts(),
            "agent": "orchestrator",
            "recap_state": "dry_run",
            "task_name": "dry_run_simulation",
            "model": "dry_run",
            "temperature": float(temperature),
            "attempt": 1,
            "steps": 1,
            "messages_preview": [
                {"role": "system", "content": "DRY RUN — synthetic request."},
                {
                    "role": "user",
                    "content": (user_request or "").strip()[:240],
                },
            ],
        },
    )
    store.append_event(
        run_id,
        "llm_response",
        {
            "ts": _now_ts(),
            "agent": "orchestrator",
            "recap_state": "dry_run",
            "task_name": "dry_run_simulation",
            "attempt": 1,
            "steps": 1,
            "content": "DRY RUN — synthetic response.",
            "raw": {"note": "synthetic"},
        },
    )

    # More realistic evidence shape: one kb_query per kb namespace.
    def _group_by_kb(chunks: Iterable[DryRunEvidenceChunk]) -> dict[str, list[DryRunEvidenceChunk]]:
        out: dict[str, list[DryRunEvidenceChunk]] = {}
        for c in chunks:
            out.setdefault(c.kb_namespace, []).append(c)
        return out

    for kb_namespace, group in _group_by_kb(evidence_chunks).items():
        store.append_event(
            run_id,
            "kb_query",
            {
                "ts": _now_ts(),
                "agent": "orchestrator",
                "kb_namespace": kb_namespace,
                "query": "DRY RUN synthetic query",
                "mode": "mix",
                "top_k": len(group),
                "results": [
                    {
                        "alias": c.alias,
                        "ref": c.ref,
                        "source": c.source,
                        "content": c.content,
                        "kb_namespace": c.kb_namespace,
                        "lightrag_chunk_id": c.lightrag_chunk_id,
                    }
                    for c in group
                ],
            },
        )

    recipes_json, citations = _build_placeholder_output(
        recipes_per_run=int(recipes_per_run),
        evidence=evidence_chunks,
    )
    return recipes_json, citations

