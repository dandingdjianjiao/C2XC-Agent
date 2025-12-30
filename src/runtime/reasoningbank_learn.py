from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import dataclass
from typing import Any, cast

from src.config.load_config import AppConfig
from src.llm.openai_compat import OpenAICompatibleChatClient
from src.runtime.reasoningbank_jobs import rollback_rb_delta
from src.storage.reasoningbank_store import MemoryItem, ReasoningBankError, ReasoningBankStore
from src.storage.sqlite_store import SQLiteStore
from src.utils.json_extract import JSONExtractionError, extract_first_json_object
from src.utils.template import render_template


class RBLearnError(RuntimeError):
    pass


@dataclass(frozen=True)
class RBLearnSnapshot:
    """Immutable snapshot for a single RB learn job (prevents mixed reads)."""

    snapshot_version: int
    run_id: str
    rb_job_id: str
    trace_cutoff_ts: float
    feedback_id: str
    feedback_updated_at: float
    final_output_event_id: str | None


@dataclass
class RBLearnDerefBudget:
    max_calls_total: int
    max_full_calls: int
    max_chars_total: int
    excerpt_chars: int
    full_chars: int

    used_calls_total: int = 0
    used_full_calls: int = 0
    used_chars_total: int = 0

    def _consume(self, *, full: bool, n_chars: int) -> None:
        self.used_calls_total += 1
        if full:
            self.used_full_calls += 1
        self.used_chars_total += max(0, int(n_chars))

    def can_open_any(self) -> bool:
        return self.used_calls_total < int(self.max_calls_total) and self.used_chars_total < int(self.max_chars_total)

    def can_open_full(self) -> bool:
        return self.used_full_calls < int(self.max_full_calls) and self.can_open_any()


_FORBIDDEN_TRACE_EVENT_TYPES = {
    # Main run model logs.
    "llm_request",
    "llm_response",
    # RB learn model logs (this module).
    "rb_llm_request",
    "rb_llm_response",
}


def _normalize_alias(value: str) -> str:
    s = (value or "").strip()
    if s.startswith("[") and s.endswith("]") and len(s) >= 3:
        s = s[1:-1].strip()
    return s


def _clamp_int(value: Any, *, default: int, min_v: int, max_v: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = int(default)
    if v < int(min_v):
        return int(min_v)
    if v > int(max_v):
        return int(max_v)
    return int(v)


def _truncate_strings(value: Any, *, max_len: int) -> Any:
    if isinstance(value, str):
        return _truncate(value, max_len=int(max_len))
    if isinstance(value, list):
        return [_truncate_strings(v, max_len=max_len) for v in value]
    if isinstance(value, dict):
        return {k: _truncate_strings(v, max_len=max_len) for k, v in value.items()}
    return value


def _sanitize_event_payload(event_type: str, payload: Any, *, max_str_len: int) -> dict[str, Any]:
    obj = payload if isinstance(payload, dict) else {}

    et = str(event_type or "").strip()
    if et == "recap_info":
        # Treat recap_info as "facts": keep what was done and the result; drop internal "think" if present.
        cleaned = dict(obj)
        cleaned.pop("think", None)
        return cast(dict[str, Any], _truncate_strings(cleaned, max_len=max_str_len))

    # Default: keep payload but truncate string fields to control size.
    return cast(dict[str, Any], _truncate_strings(obj, max_len=max_str_len))


def _rb_learn_deref_tools_schema() -> list[dict[str, Any]]:
    """Tool schemas for the RB learn extractor (B-scheme: factual originals only)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "rb_list_events",
                "description": (
                    "List factual trace events available for this run within the RB learn snapshot. "
                    "Use this to discover event_id values to open. "
                    "NOTE: LLM request/response logs are not accessible."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "event_types": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rb_open_event",
                "description": (
                    "Open a factual trace event by event_id (within snapshot cutoff). "
                    "Forbidden: llm_request/llm_response and rb_llm_request/rb_llm_response."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "event_id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["excerpt", "full"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["event_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rb_open_memory",
                "description": "Open a ReasoningBank memory by mem_id (original content from Chroma).",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mem_id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["excerpt", "full"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["mem_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rb_open_evidence",
                "description": (
                    "Open KB evidence chunk text by alias (e.g. C12) or canonical ref (kb:...). "
                    "This returns the original chunk content recorded during the run."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "alias": {"type": "string"},
                        "ref": {"type": "string"},
                        "mode": {"type": "string", "enum": ["excerpt", "full"]},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rb_open_feedback",
                "description": "Open the experiment feedback JSON (factual record).",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mode": {"type": "string", "enum": ["excerpt", "full"]},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rb_open_run_output",
                "description": "Open the run final_output JSON (factual record).",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mode": {"type": "string", "enum": ["excerpt", "full"]},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
    ]


@dataclass
class _RBLearnDerefContext:
    store: SQLiteStore
    rb: ReasoningBankStore
    cfg: AppConfig
    snapshot: RBLearnSnapshot
    budget: RBLearnDerefBudget
    feedback_payload: dict[str, Any]
    run_output_json: dict[str, Any]


def _tool_error(*, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": {"code": str(code), "message": str(message)}}
    if details:
        out["error"]["details"] = details
    return out


def _append_rb_source_opened(
    ctx: _RBLearnDerefContext,
    *,
    source_type: str,
    source_id: str,
    mode_requested: str,
    mode_used: str,
    truncated: bool,
    returned_chars: int,
    reason: str | None,
    error_code: str | None = None,
) -> None:
    ctx.store.append_event(
        ctx.snapshot.run_id,
        "rb_source_opened",
        {
            "ts": time.time(),
            "rb_job_id": ctx.snapshot.rb_job_id,
            "snapshot_version": int(ctx.snapshot.snapshot_version),
            "trace_cutoff_ts": float(ctx.snapshot.trace_cutoff_ts),
            "feedback_id": ctx.snapshot.feedback_id,
            "feedback_updated_at": float(ctx.snapshot.feedback_updated_at),
            "final_output_event_id": ctx.snapshot.final_output_event_id,
            "source_type": str(source_type),
            "source_id": str(source_id),
            "mode_requested": str(mode_requested),
            "mode_used": str(mode_used),
            "truncated": bool(truncated),
            "returned_chars": int(returned_chars),
            "error_code": str(error_code) if error_code else None,
            "reason": str(reason or "") or None,
            "budget": {
                "used_calls_total": int(ctx.budget.used_calls_total),
                "used_full_calls": int(ctx.budget.used_full_calls),
                "used_chars_total": int(ctx.budget.used_chars_total),
                "max_calls_total": int(ctx.budget.max_calls_total),
                "max_full_calls": int(ctx.budget.max_full_calls),
                "max_chars_total": int(ctx.budget.max_chars_total),
            },
        },
    )


def _resolve_mode(ctx: _RBLearnDerefContext, mode_raw: Any) -> tuple[str, int, bool]:
    requested = str(mode_raw or "").strip().lower() or "excerpt"
    if requested not in {"excerpt", "full"}:
        requested = "excerpt"

    if not ctx.budget.can_open_any():
        return ("blocked", 0, False)

    if requested == "full" and not ctx.budget.can_open_full():
        return ("excerpt", int(ctx.budget.excerpt_chars), True)

    used_mode = requested
    max_chars = int(ctx.budget.full_chars) if used_mode == "full" else int(ctx.budget.excerpt_chars)
    return (used_mode, max_chars, False)


def _deref_list_events(ctx: _RBLearnDerefContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.budget.can_open_any():
        out = _tool_error(
            code="budget_exceeded",
            message="Cannot list events: dereference budget exhausted.",
            details={"budget": {"max_calls_total": ctx.budget.max_calls_total}},
        )
        _append_rb_source_opened(
            ctx,
            source_type="trace_events",
            source_id="list",
            mode_requested="excerpt",
            mode_used="blocked",
            truncated=False,
            returned_chars=len(json.dumps(out, ensure_ascii=False)),
            reason=str(args.get("reason") or ""),
            error_code="budget_exceeded",
        )
        return out

    requested_types = args.get("event_types")
    event_types: list[str] | None = None
    if isinstance(requested_types, list):
        event_types = [str(t) for t in requested_types if str(t).strip()]
        if not event_types:
            event_types = None

    # Default: show "most useful factual events" for learning.
    default_types = [
        "final_output",
        "run_failed",
        "recap_info",
        "kb_query",
        "kb_get",
        "kb_list",
        "mem_search",
        "mem_get",
        "mem_list",
        "citations_resolved",
        "memories_resolved",
    ]
    effective_types = event_types or default_types

    filtered: list[str] = []
    blocked: list[str] = []
    for t in effective_types:
        et = str(t).strip()
        if not et:
            continue
        if et in _FORBIDDEN_TRACE_EVENT_TYPES or et.startswith("llm_") or et.startswith("rb_llm_"):
            blocked.append(et)
            continue
        filtered.append(et)

    limit = _clamp_int(
        args.get("limit"),
        default=int(ctx.cfg.reasoningbank.learn_deref_list_events_default_limit),
        min_v=1,
        max_v=int(ctx.cfg.reasoningbank.learn_deref_list_events_max_limit),
    )

    rows: list[dict[str, Any]] = []
    if filtered:
        rows = ctx.store.list_latest_events(
            run_id=ctx.snapshot.run_id,
            limit=int(limit),
            event_types=filtered,
            include_payload=True,
            until=float(ctx.snapshot.trace_cutoff_ts),
        )

    items: list[dict[str, Any]] = []
    for r in rows:
        et = str(r.get("event_type") or "")
        payload = r.get("payload")
        summary = ""
        if isinstance(payload, dict):
            if et == "kb_query":
                q = _truncate(str(payload.get("query") or ""), max_len=160)
                kb_name = str(payload.get("kb_name") or payload.get("kb_namespace") or "")
                agent = str(payload.get("agent") or "")
                summary = f"agent={agent} kb={kb_name} query={q}"
            elif et == "recap_info":
                agent = str(payload.get("agent") or "")
                task_name = str(payload.get("task_name") or "")
                recap_state = str(payload.get("recap_state") or "")
                summary = f"agent={agent} state={recap_state} task={task_name}"
            elif et == "mem_search":
                q = _truncate(str(payload.get("query") or ""), max_len=160)
                agent = str(payload.get("agent") or "")
                summary = f"agent={agent} query={q}"
            elif et == "final_output":
                recipes_json = payload.get("recipes_json")
                n_recipes = 0
                if isinstance(recipes_json, dict) and isinstance(recipes_json.get("recipes"), list):
                    n_recipes = len(recipes_json.get("recipes") or [])
                summary = f"recipes={n_recipes}"
            elif et == "run_failed":
                err = _truncate(str(payload.get("error") or ""), max_len=160)
                summary = f"error={err}"
        items.append(
            {
                "event_id": str(r.get("event_id") or ""),
                "created_at": float(r.get("created_at") or 0.0),
                "event_type": et,
                "summary": summary,
            }
        )

    out: dict[str, Any] = {
        "ok": True,
        "snapshot": {
            "trace_cutoff_ts": float(ctx.snapshot.trace_cutoff_ts),
            "feedback_id": ctx.snapshot.feedback_id,
            "feedback_updated_at": float(ctx.snapshot.feedback_updated_at),
        },
        "blocked_event_types": blocked,
        "items": items,
    }
    out_s = json.dumps(out, ensure_ascii=False)
    ctx.budget._consume(full=False, n_chars=len(out_s))
    _append_rb_source_opened(
        ctx,
        source_type="trace_events",
        source_id="list",
        mode_requested="excerpt",
        mode_used="excerpt",
        truncated=False,
        returned_chars=len(out_s),
        reason=str(args.get("reason") or ""),
    )
    return out


def _deref_open_event(ctx: _RBLearnDerefContext, args: dict[str, Any]) -> dict[str, Any]:
    event_id = str(args.get("event_id") or "").strip()
    if not event_id:
        out = _tool_error(code="invalid_argument", message="event_id is required.")
        ctx.budget._consume(full=False, n_chars=len(json.dumps(out, ensure_ascii=False)))
        return out

    used_mode, max_chars, degraded = _resolve_mode(ctx, args.get("mode"))
    if used_mode == "blocked":
        out = _tool_error(code="budget_exceeded", message="Cannot open event: dereference budget exhausted.")
        _append_rb_source_opened(
            ctx,
            source_type="event",
            source_id=event_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used="blocked",
            truncated=False,
            returned_chars=len(json.dumps(out, ensure_ascii=False)),
            reason=str(args.get("reason") or ""),
            error_code="budget_exceeded",
        )
        return out

    row = ctx.store.get_event(run_id=ctx.snapshot.run_id, event_id=event_id)
    if row is None:
        out = _tool_error(code="not_found", message="Event not found.")
        out_s = json.dumps(out, ensure_ascii=False)
        ctx.budget._consume(full=False, n_chars=len(out_s))
        _append_rb_source_opened(
            ctx,
            source_type="event",
            source_id=event_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used=used_mode,
            truncated=False,
            returned_chars=len(out_s),
            reason=str(args.get("reason") or ""),
            error_code="not_found",
        )
        return out

    created_at = float(row["created_at"])
    if created_at > float(ctx.snapshot.trace_cutoff_ts):
        out = _tool_error(
            code="snapshot_out_of_bounds",
            message="Event is outside the RB learn snapshot cutoff (newer than trace_cutoff_ts).",
            details={"event_created_at": created_at, "trace_cutoff_ts": float(ctx.snapshot.trace_cutoff_ts)},
        )
        out_s = json.dumps(out, ensure_ascii=False)
        ctx.budget._consume(full=False, n_chars=len(out_s))
        _append_rb_source_opened(
            ctx,
            source_type="event",
            source_id=event_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used=used_mode,
            truncated=False,
            returned_chars=len(out_s),
            reason=str(args.get("reason") or ""),
            error_code="snapshot_out_of_bounds",
        )
        return out

    event_type = str(row["event_type"])
    if event_type in _FORBIDDEN_TRACE_EVENT_TYPES or event_type.startswith("llm_") or event_type.startswith("rb_llm_"):
        out = _tool_error(
            code="forbidden_event_type",
            message=f"Access to event_type={event_type!r} is forbidden in RB learn (facts-only policy).",
            details={"event_type": event_type},
        )
        out_s = json.dumps(out, ensure_ascii=False)
        ctx.budget._consume(full=False, n_chars=len(out_s))
        _append_rb_source_opened(
            ctx,
            source_type="event",
            source_id=event_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used=used_mode,
            truncated=False,
            returned_chars=len(out_s),
            reason=str(args.get("reason") or ""),
            error_code="forbidden_event_type",
        )
        return out

    try:
        payload_any = json.loads(str(row["payload_json"] or "{}"))
    except Exception:
        payload_any = {}

    payload = _sanitize_event_payload(event_type, payload_any, max_str_len=max_chars)
    out: dict[str, Any] = {
        "ok": True,
        "event": {
            "event_id": event_id,
            "run_id": ctx.snapshot.run_id,
            "created_at": created_at,
            "event_type": event_type,
            "payload": payload,
            "mode": used_mode,
            "degraded_from_full": bool(degraded),
        },
    }
    out_s = json.dumps(out, ensure_ascii=False)
    ctx.budget._consume(full=(used_mode == "full"), n_chars=len(out_s))
    _append_rb_source_opened(
        ctx,
        source_type="event",
        source_id=event_id,
        mode_requested=str(args.get("mode") or "excerpt"),
        mode_used=used_mode,
        truncated=False,
        returned_chars=len(out_s),
        reason=str(args.get("reason") or ""),
    )
    return out


def _deref_open_memory(ctx: _RBLearnDerefContext, args: dict[str, Any]) -> dict[str, Any]:
    mem_id = str(args.get("mem_id") or "").strip()
    if not mem_id:
        out = _tool_error(code="invalid_argument", message="mem_id is required.")
        ctx.budget._consume(full=False, n_chars=len(json.dumps(out, ensure_ascii=False)))
        return out

    used_mode, max_chars, degraded = _resolve_mode(ctx, args.get("mode"))
    if used_mode == "blocked":
        out = _tool_error(code="budget_exceeded", message="Cannot open memory: dereference budget exhausted.")
        _append_rb_source_opened(
            ctx,
            source_type="memory",
            source_id=mem_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used="blocked",
            truncated=False,
            returned_chars=len(json.dumps(out, ensure_ascii=False)),
            reason=str(args.get("reason") or ""),
            error_code="budget_exceeded",
        )
        return out

    item = ctx.rb.get(mem_id=mem_id)
    if item is None:
        out = _tool_error(code="not_found", message="Memory not found.")
        out_s = json.dumps(out, ensure_ascii=False)
        ctx.budget._consume(full=False, n_chars=len(out_s))
        _append_rb_source_opened(
            ctx,
            source_type="memory",
            source_id=mem_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used=used_mode,
            truncated=False,
            returned_chars=len(out_s),
            reason=str(args.get("reason") or ""),
            error_code="not_found",
        )
        return out

    full_text = str(item.content or "")
    truncated = len(full_text) > int(max_chars)
    content = _truncate(full_text, max_len=int(max_chars))

    out: dict[str, Any] = {
        "ok": True,
        "memory": {
            "mem_id": item.mem_id,
            "status": item.status,
            "role": item.role,
            "type": item.type,
            "source_run_id": item.source_run_id,
            "created_at": float(item.created_at),
            "updated_at": float(item.updated_at),
            "schema_version": int(item.schema_version),
            "content": content,
            "mode": used_mode,
            "truncated": bool(truncated),
            "degraded_from_full": bool(degraded),
        },
    }
    out_s = json.dumps(out, ensure_ascii=False)
    ctx.budget._consume(full=(used_mode == "full"), n_chars=len(out_s))
    _append_rb_source_opened(
        ctx,
        source_type="memory",
        source_id=mem_id,
        mode_requested=str(args.get("mode") or "excerpt"),
        mode_used=used_mode,
        truncated=bool(truncated),
        returned_chars=len(out_s),
        reason=str(args.get("reason") or ""),
    )
    return out


def _find_kb_evidence_in_run(
    store: SQLiteStore,
    *,
    run_id: str,
    trace_cutoff_ts: float,
    alias: str | None,
    ref: str | None,
) -> dict[str, Any] | None:
    want_alias = _normalize_alias(alias or "")
    want_ref = str(ref or "").strip()

    cursor: tuple[float, str] | None = None
    while True:
        page = store.list_events_page(
            run_id=run_id,
            limit=200,
            cursor=cursor,
            event_types=["kb_query"],
            include_payload=True,
            since=None,
            until=float(trace_cutoff_ts),
        )
        items = page.get("items") or []
        for ev in items:
            payload = ev.get("payload")
            if not isinstance(payload, dict):
                continue
            results = payload.get("results")
            if not isinstance(results, list):
                continue
            for r in results:
                if not isinstance(r, dict):
                    continue
                a = _normalize_alias(str(r.get("alias") or ""))
                rr = str(r.get("ref") or "").strip()
                if want_alias and a == want_alias:
                    return dict(r)
                if want_ref and rr and rr == want_ref:
                    return dict(r)

        if not bool(page.get("has_more")):
            return None

        last = items[-1]
        cursor = (float(last.get("created_at") or 0.0), str(last.get("event_id") or ""))


def _deref_open_evidence(ctx: _RBLearnDerefContext, args: dict[str, Any]) -> dict[str, Any]:
    alias = str(args.get("alias") or "").strip()
    ref = str(args.get("ref") or "").strip()

    if bool(alias) == bool(ref):
        out = _tool_error(code="invalid_argument", message="Provide exactly one of {alias, ref}.")
        ctx.budget._consume(full=False, n_chars=len(json.dumps(out, ensure_ascii=False)))
        return out

    used_mode, max_chars, degraded = _resolve_mode(ctx, args.get("mode"))
    if used_mode == "blocked":
        out = _tool_error(code="budget_exceeded", message="Cannot open evidence: dereference budget exhausted.")
        _append_rb_source_opened(
            ctx,
            source_type="evidence",
            source_id=alias or ref,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used="blocked",
            truncated=False,
            returned_chars=len(json.dumps(out, ensure_ascii=False)),
            reason=str(args.get("reason") or ""),
            error_code="budget_exceeded",
        )
        return out

    found = _find_kb_evidence_in_run(
        ctx.store,
        run_id=ctx.snapshot.run_id,
        trace_cutoff_ts=float(ctx.snapshot.trace_cutoff_ts),
        alias=alias if alias else None,
        ref=ref if ref else None,
    )
    if found is None:
        out = _tool_error(code="not_found", message="Evidence not found in run trace (kb_query).")
        out_s = json.dumps(out, ensure_ascii=False)
        ctx.budget._consume(full=False, n_chars=len(out_s))
        _append_rb_source_opened(
            ctx,
            source_type="evidence",
            source_id=alias or ref,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used=used_mode,
            truncated=False,
            returned_chars=len(out_s),
            reason=str(args.get("reason") or ""),
            error_code="not_found",
        )
        return out

    content_full = str(found.get("content") or "")
    truncated = len(content_full) > int(max_chars)
    content = _truncate(content_full, max_len=int(max_chars))

    out: dict[str, Any] = {
        "ok": True,
        "evidence": {
            "alias": _normalize_alias(str(found.get("alias") or "")),
            "ref": str(found.get("ref") or ""),
            "source": str(found.get("source") or ""),
            "kb_namespace": str(found.get("kb_namespace") or ""),
            "lightrag_chunk_id": str(found.get("lightrag_chunk_id") or "") or None,
            "content": content,
            "mode": used_mode,
            "truncated": bool(truncated),
            "degraded_from_full": bool(degraded),
        },
    }
    out_s = json.dumps(out, ensure_ascii=False)
    ctx.budget._consume(full=(used_mode == "full"), n_chars=len(out_s))
    _append_rb_source_opened(
        ctx,
        source_type="evidence",
        source_id=alias or ref,
        mode_requested=str(args.get("mode") or "excerpt"),
        mode_used=used_mode,
        truncated=bool(truncated),
        returned_chars=len(out_s),
        reason=str(args.get("reason") or ""),
    )
    return out


def _deref_open_feedback(ctx: _RBLearnDerefContext, args: dict[str, Any]) -> dict[str, Any]:
    used_mode, max_chars, degraded = _resolve_mode(ctx, args.get("mode"))
    if used_mode == "blocked":
        out = _tool_error(code="budget_exceeded", message="Cannot open feedback: dereference budget exhausted.")
        _append_rb_source_opened(
            ctx,
            source_type="feedback",
            source_id=ctx.snapshot.feedback_id,
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used="blocked",
            truncated=False,
            returned_chars=len(json.dumps(out, ensure_ascii=False)),
            reason=str(args.get("reason") or ""),
            error_code="budget_exceeded",
        )
        return out

    payload = _truncate_strings(ctx.feedback_payload, max_len=max_chars)
    out: dict[str, Any] = {
        "ok": True,
        "feedback": payload,
        "mode": used_mode,
        "degraded_from_full": bool(degraded),
    }
    out_s = json.dumps(out, ensure_ascii=False)
    ctx.budget._consume(full=(used_mode == "full"), n_chars=len(out_s))
    _append_rb_source_opened(
        ctx,
        source_type="feedback",
        source_id=ctx.snapshot.feedback_id,
        mode_requested=str(args.get("mode") or "excerpt"),
        mode_used=used_mode,
        truncated=False,
        returned_chars=len(out_s),
        reason=str(args.get("reason") or ""),
    )
    return out


def _deref_open_run_output(ctx: _RBLearnDerefContext, args: dict[str, Any]) -> dict[str, Any]:
    used_mode, max_chars, degraded = _resolve_mode(ctx, args.get("mode"))
    if used_mode == "blocked":
        out = _tool_error(code="budget_exceeded", message="Cannot open run output: dereference budget exhausted.")
        _append_rb_source_opened(
            ctx,
            source_type="run_output",
            source_id=ctx.snapshot.final_output_event_id or "",
            mode_requested=str(args.get("mode") or "excerpt"),
            mode_used="blocked",
            truncated=False,
            returned_chars=len(json.dumps(out, ensure_ascii=False)),
            reason=str(args.get("reason") or ""),
            error_code="budget_exceeded",
        )
        return out

    payload = _truncate_strings(ctx.run_output_json, max_len=max_chars)
    out: dict[str, Any] = {
        "ok": True,
        "run_output": payload,
        "mode": used_mode,
        "degraded_from_full": bool(degraded),
    }
    out_s = json.dumps(out, ensure_ascii=False)
    ctx.budget._consume(full=(used_mode == "full"), n_chars=len(out_s))
    _append_rb_source_opened(
        ctx,
        source_type="run_output",
        source_id=ctx.snapshot.final_output_event_id or "",
        mode_requested=str(args.get("mode") or "excerpt"),
        mode_used=used_mode,
        truncated=False,
        returned_chars=len(out_s),
        reason=str(args.get("reason") or ""),
    )
    return out


def _execute_deref_tool(ctx: _RBLearnDerefContext, *, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "rb_list_events":
        return _deref_list_events(ctx, args)
    if name == "rb_open_event":
        return _deref_open_event(ctx, args)
    if name == "rb_open_memory":
        return _deref_open_memory(ctx, args)
    if name == "rb_open_evidence":
        return _deref_open_evidence(ctx, args)
    if name == "rb_open_feedback":
        return _deref_open_feedback(ctx, args)
    if name == "rb_open_run_output":
        return _deref_open_run_output(ctx, args)
    return _tool_error(code="unknown_tool", message=f"Unknown tool: {name}")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


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


def _sync_rb_mem_index(store: SQLiteStore, item: MemoryItem) -> None:
    store.upsert_rb_mem_index(
        mem_id=item.mem_id,
        created_at=float(item.created_at),
        updated_at=float(item.updated_at),
        status=str(item.status),
        role=str(item.role),
        type=str(item.type),
        source_run_id=str(item.source_run_id or "") or None,
        schema_version=int(item.schema_version),
    )


def _truncate(text: str, *, max_len: int) -> str:
    s = str(text or "")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _latest_event_payload(
    store: SQLiteStore,
    *,
    run_id: str,
    event_type: str,
    until: float | None,
) -> dict[str, Any] | None:
    rows = store.list_latest_events(
        run_id=run_id,
        limit=1,
        event_types=[event_type],
        include_payload=True,
        until=until,
    )
    if not rows:
        return None
    payload = rows[0].get("payload")
    return payload if isinstance(payload, dict) else None


def _shrink_kb_query_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # kb_query payload may include full chunk content; keep only lightweight metadata.
    out: dict[str, Any] = {}
    out["ts"] = payload.get("ts")
    out["agent"] = payload.get("agent")
    out["kb_name"] = payload.get("kb_name")
    out["mode"] = payload.get("mode")
    out["top_k"] = payload.get("top_k")
    out["query"] = _truncate(str(payload.get("query") or ""), max_len=320)

    results = payload.get("results")
    if isinstance(results, list):
        slim: list[dict[str, Any]] = []
        for r in results[:12]:
            if not isinstance(r, dict):
                continue
            slim.append(
                {
                    "alias": str(r.get("alias") or ""),
                    "ref": str(r.get("ref") or ""),
                    "source": str(r.get("source") or ""),
                    "kb_namespace": str(r.get("kb_namespace") or ""),
                    "lightrag_chunk_id": str(r.get("lightrag_chunk_id") or "") or None,
                }
            )
        out["results"] = slim
    return out


def _build_run_trace_digest(store: SQLiteStore, *, snapshot: RBLearnSnapshot) -> dict[str, Any]:
    """Build a compact trace digest to make RB extraction more 'experience-driven'.

    This is intentionally lightweight:
    - No raw LLM prompts/responses
    - No full KB chunk content
    - Focus on tool usage + resolved citations/memories
    """
    rid = (snapshot.run_id or "").strip()
    if not rid:
        return {}

    event_counts = store.count_event_types_for_run(run_id=rid, until=float(snapshot.trace_cutoff_ts))

    latest_mem_search = _latest_event_payload(store, run_id=rid, event_type="mem_search", until=snapshot.trace_cutoff_ts)
    latest_memories_resolved = _latest_event_payload(store, run_id=rid, event_type="memories_resolved", until=snapshot.trace_cutoff_ts)
    latest_citations_resolved = _latest_event_payload(store, run_id=rid, event_type="citations_resolved", until=snapshot.trace_cutoff_ts)
    latest_run_failed = _latest_event_payload(store, run_id=rid, event_type="run_failed", until=snapshot.trace_cutoff_ts)

    recent_kb_queries_raw = store.list_latest_events(
        run_id=rid,
        limit=3,
        event_types=["kb_query"],
        include_payload=True,
        until=snapshot.trace_cutoff_ts,
    )
    recent_kb_queries: list[dict[str, Any]] = []
    for e in recent_kb_queries_raw:
        payload = e.get("payload")
        if isinstance(payload, dict):
            recent_kb_queries.append(_shrink_kb_query_payload(payload))

    return {
        "snapshot": {
            "snapshot_version": int(snapshot.snapshot_version),
            "trace_cutoff_ts": float(snapshot.trace_cutoff_ts),
            "feedback_id": snapshot.feedback_id,
            "feedback_updated_at": float(snapshot.feedback_updated_at),
            "final_output_event_id": snapshot.final_output_event_id,
        },
        "event_counts": event_counts,
        "latest_mem_search": latest_mem_search,
        "latest_memories_resolved": latest_memories_resolved,
        "latest_citations_resolved": latest_citations_resolved,
        "recent_kb_queries": recent_kb_queries,
        "latest_run_failed": latest_run_failed,
    }


def _extractor_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "rb_extract_items",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "role": {
                                    "type": "string",
                                    "enum": ["global", "orchestrator", "mof_expert", "tio2_expert"],
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["reasoningbank_item", "manual_note"],
                                },
                                "content": {"type": "string", "minLength": 1},
                                "extra": {"type": "object"},
                            },
                            "required": ["role", "type", "content"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    }


def _merge_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "rb_merge_result",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "content": {"type": "string", "minLength": 1},
                    "extra": {"type": "object"},
                },
                "required": ["content"],
            },
        },
    }


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _best_effort_similarity(distance: float | None) -> float | None:
    """Convert Chroma distance into a similarity-like score.

    Assumption (common case): cosine distance in [0..2], where lower is better.
    Similarity ~= 1 - distance.
    """
    if distance is None:
        return None
    try:
        return 1.0 - float(distance)
    except Exception:
        return None


def _format_existing_memories(cfg: AppConfig, items: list[MemoryItem]) -> str:
    tpl = cfg.reasoningbank.context_template
    lines: list[str] = []
    for it in items:
        lines.append(
            render_template(
                tpl,
                {
                    "mem_id": it.mem_id,
                    "status": it.status,
                    "role": it.role,
                    "type": it.type,
                    "source_run_id": it.source_run_id or "",
                    "content": it.content,
                },
            ).strip()
        )
    return "\n\n".join([l for l in lines if l]).strip()


def _system_prompt(cfg: AppConfig) -> str:
    return "\n\n".join(
        [
            cfg.prompts.system_base.strip(),
            cfg.priors.system_description_md.strip(),
            cfg.priors.microenvironment_tio2_md.strip(),
            cfg.priors.microenvironment_mof_md.strip(),
        ]
    ).strip()


def _dry_run_extract_items(run_id: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "global",
            "type": "reasoningbank_item",
            "content": (
                "DRY RUN — synthetic ReasoningBank memory item.\n"
                "Purpose: validate RB browse/learn/rollback pipeline.\n"
                f"source_run_id={run_id}"
            ),
            "extra": {"dry_run": True, "confidence": 0.0, "tags": ["dry_run"]},
        },
        {
            "role": "orchestrator",
            "type": "reasoningbank_item",
            "content": (
                "DRY RUN — synthetic orchestrator memory.\n"
                "Do not use for science."
            ),
            "extra": {"dry_run": True, "confidence": 0.0, "tags": ["dry_run"]},
        },
    ]


def learn_reasoningbank_for_run(
    store: SQLiteStore,
    *,
    rb: ReasoningBankStore,
    cfg: AppConfig,
    llm: OpenAICompatibleChatClient | None,
    run_id: str,
    rb_job_id: str,
) -> str:
    """Perform RB learn for a run and return the new delta_id.

    Implements:
      - strict rollback of previous applied deltas for this run
      - retrieval (existing memories)
      - extraction (LLM or dry-run)
      - consolidation (near-duplicate merge via LLM when available)
      - delta recording (SQLite)
    """
    rid = (run_id or "").strip()
    if not rid:
        raise RBLearnError("run_id is required.")
    if store.get_run(run_id=rid) is None:
        raise RBLearnError("Run not found.")

    trace_cutoff_ts = time.time()

    feedback_payload = store.get_feedback_for_run(run_id=rid)
    if feedback_payload is None:
        raise RBLearnError("Feedback not found (required for RB learn).")

    out_row = store.get_latest_event(run_id=rid, event_type="final_output")
    run_output_json: dict[str, Any] = {}
    final_output_event_id: str | None = None
    if out_row is not None:
        try:
            final_output_event_id = str(out_row["event_id"])
        except Exception:
            final_output_event_id = None
        try:
            run_output_json = json.loads(str(out_row["payload_json"]))
        except Exception:
            run_output_json = {}

    fb = feedback_payload.get("feedback") if isinstance(feedback_payload, dict) else None
    fb_id = str((fb or {}).get("feedback_id") or "").strip()
    fb_updated_at = float((fb or {}).get("updated_at") or 0.0)
    snapshot = RBLearnSnapshot(
        snapshot_version=1,
        run_id=rid,
        rb_job_id=rb_job_id,
        trace_cutoff_ts=float(trace_cutoff_ts),
        feedback_id=fb_id,
        feedback_updated_at=fb_updated_at,
        final_output_event_id=final_output_event_id,
    )

    budget = RBLearnDerefBudget(
        max_calls_total=int(cfg.reasoningbank.learn_deref_max_calls_total),
        max_full_calls=int(cfg.reasoningbank.learn_deref_max_full_calls),
        max_chars_total=int(cfg.reasoningbank.learn_deref_max_chars_total),
        excerpt_chars=int(cfg.reasoningbank.learn_deref_excerpt_chars),
        full_chars=int(cfg.reasoningbank.learn_deref_full_chars),
    )

    store.append_event(
        rid,
        "rb_learn_snapshot",
        {
            "ts": time.time(),
            "rb_job_id": rb_job_id,
            "snapshot": {
                "snapshot_version": int(snapshot.snapshot_version),
                "trace_cutoff_ts": float(snapshot.trace_cutoff_ts),
                "feedback_id": snapshot.feedback_id,
                "feedback_updated_at": float(snapshot.feedback_updated_at),
                "final_output_event_id": snapshot.final_output_event_id,
            },
            "budget": {
                "max_calls_total": int(budget.max_calls_total),
                "max_full_calls": int(budget.max_full_calls),
                "max_chars_total": int(budget.max_chars_total),
                "excerpt_chars": int(budget.excerpt_chars),
                "full_chars": int(budget.full_chars),
            },
            "policy": {
                "facts_only": True,
                "forbidden_trace_event_types": sorted(_FORBIDDEN_TRACE_EVENT_TYPES),
            },
        },
    )

    # Strict rollback: ensure the current RB state for this run is reverted to pre-learn before re-learning.
    deltas = store.list_rb_deltas_for_run(run_id=rid)
    applied_delta_ids = [str(d["delta_id"]) for d in deltas if str(d.get("status") or "") == "applied"]
    for did in applied_delta_ids:
        rollback_rb_delta(
            store,
            rb=rb,
            run_id=rid,
            delta_id=did,
            reason="auto_rollback_before_relearn",
        )

    # Retrieval: a small set of existing active memories for de-duplication context.
    query_seed = json.dumps(
        {
            "run_id": rid,
            "run_output": run_output_json.get("recipes_json") or {},
            "feedback": feedback_payload.get("feedback") or {},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    retrieved = rb.query(
        query=query_seed,
        n_results=10,
        status=["active"],
        role=None,
        type=None,
    )
    retrieved_items = [cast(MemoryItem, r["item"]) for r in retrieved]
    existing_context = _format_existing_memories(cfg, retrieved_items[:8])

    dry_run = _env_bool("C2XC_RB_LEARN_DRY_RUN", False)
    extracted_items: list[dict[str, Any]]

    if dry_run:
        extracted_items = _dry_run_extract_items(rid)
    else:
        if llm is None:
            raise RBLearnError("LLM is required for RB learn (set C2XC_RB_LEARN_DRY_RUN=1 for dry-run mode).")

        trace_digest = _build_run_trace_digest(store, snapshot=snapshot)
        prompt = render_template(
            cfg.reasoningbank.extract_prompt_template,
            {
                "run_id": rid,
                "run_output_json": json.dumps(run_output_json, ensure_ascii=False, indent=2),
                "feedback_json": json.dumps(feedback_payload, ensure_ascii=False, indent=2),
                "existing_memories_context": existing_context,
                "run_trace_digest_json": json.dumps(trace_digest, ensure_ascii=False, indent=2),
            },
        ).strip()

        system = _system_prompt(cfg)
        tools = _rb_learn_deref_tools_schema()
        deref_ctx = _RBLearnDerefContext(
            store=store,
            rb=rb,
            cfg=cfg,
            snapshot=snapshot,
            budget=budget,
            feedback_payload=feedback_payload,
            run_output_json=run_output_json,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        max_turns = 12
        turn = 0
        raw_content: str | None = None
        while True:
            store.append_event(
                rid,
                "rb_llm_request",
                {
                    "ts": time.time(),
                    "rb_job_id": rb_job_id,
                    "purpose": "extract",
                    "turn": int(turn),
                    "model": getattr(llm, "model", None),
                    "base_url": getattr(llm, "base_url", None),
                    "temperature": 0.2,
                    "response_schema": "rb_extract_items",
                    "snapshot": {
                        "snapshot_version": int(snapshot.snapshot_version),
                        "trace_cutoff_ts": float(snapshot.trace_cutoff_ts),
                        "feedback_id": snapshot.feedback_id,
                        "feedback_updated_at": float(snapshot.feedback_updated_at),
                        "final_output_event_id": snapshot.final_output_event_id,
                    },
                    "budget": {
                        "used_calls_total": int(budget.used_calls_total),
                        "used_full_calls": int(budget.used_full_calls),
                        "used_chars_total": int(budget.used_chars_total),
                        "max_calls_total": int(budget.max_calls_total),
                        "max_full_calls": int(budget.max_full_calls),
                        "max_chars_total": int(budget.max_chars_total),
                    },
                    # Store full system+prompt only on turn0 to avoid repeated large payloads.
                    "system": system if turn == 0 else None,
                    "prompt": prompt if turn == 0 else None,
                    "n_messages": len(messages),
                },
            )

            extra: dict[str, Any] = {"tools": tools, "tool_choice": "auto"}
            if not bool(getattr(llm, "enable_thinking", False)):
                extra["response_format"] = _extractor_response_format()
            try:
                raw = llm.chat_messages(messages=messages, temperature=0.2, extra=extra)
            except Exception as e:
                # Fallback: some providers do not accept response_format with tools.
                store.append_event(
                    rid,
                    "rb_llm_response",
                    {
                        "ts": time.time(),
                        "rb_job_id": rb_job_id,
                        "purpose": "extract",
                        "turn": int(turn),
                        "error": f"llm_call_failed_with_response_format: {e}",
                    },
                )
                raw = llm.chat_messages(messages=messages, temperature=0.2, extra={"tools": tools, "tool_choice": "auto"})

            store.append_event(
                rid,
                "rb_llm_response",
                {
                    "ts": time.time(),
                    "rb_job_id": rb_job_id,
                    "purpose": "extract",
                    "turn": int(turn),
                    "content": raw.content,
                    "raw": raw.raw,
                    "tool_calls": raw.tool_calls,
                },
            )

            if raw.tool_calls:
                # Append assistant tool-call message then tool outputs.
                messages.append({"role": "assistant", "content": raw.content or "", "tool_calls": raw.tool_calls})
                for tc in raw.tool_calls:
                    fn = tc.get("function") if isinstance(tc, dict) else None
                    name = str((fn or {}).get("name") or "").strip()
                    args_raw = (fn or {}).get("arguments") if isinstance(fn, dict) else ""
                    call_id = str(tc.get("id") or "").strip() or "tool_call"

                    parsed_args: dict[str, Any] = {}
                    if isinstance(args_raw, str) and args_raw.strip():
                        try:
                            obj = json.loads(args_raw)
                            parsed_args = obj if isinstance(obj, dict) else {}
                        except Exception:
                            parsed_args = {}

                    result = _execute_deref_tool(deref_ctx, name=name, args=parsed_args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )

                turn += 1
                if turn >= max_turns:
                    raise RBLearnError("RB extractor exceeded maximum tool-calling turns.")
                continue

            raw_content = raw.content
            break

        if raw_content is None:
            raise RBLearnError("RB extractor produced no content.")
        try:
            obj = extract_first_json_object(raw_content)
        except JSONExtractionError as e:
            raise RBLearnError(f"RB extract output is not valid JSON: {e}") from e

        items_any = obj.get("items") if isinstance(obj, dict) else None
        extracted_items = items_any if isinstance(items_any, list) else []

    # Consolidation + apply changes, record delta ops.
    ops: list[dict[str, Any]] = []
    for proposal in extracted_items:
        if not isinstance(proposal, dict):
            continue
        role = str(proposal.get("role") or "").strip() or "global"
        typ = str(proposal.get("type") or "").strip() or "reasoningbank_item"
        content = str(proposal.get("content") or "").strip()
        extra = _ensure_dict(proposal.get("extra"))
        if not content:
            continue

        # Find near-duplicate candidate in active memories within same role/type.
        dup_candidates = rb.query(query=content, n_results=3, status=["active"], role=[role], type=[typ])
        chosen_existing: MemoryItem | None = None
        chosen_distance: float | None = None
        if dup_candidates:
            first = dup_candidates[0]
            chosen_existing = cast(MemoryItem, first["item"])
            chosen_distance = first.get("distance")

        similarity = _best_effort_similarity(chosen_distance)
        threshold = float(cfg.reasoningbank.near_duplicate_threshold)
        dup_debug: dict[str, Any] | None = None
        if chosen_existing is not None and similarity is not None:
            dup_debug = {
                "candidate_mem_id": chosen_existing.mem_id,
                "distance": float(chosen_distance) if chosen_distance is not None else None,
                "similarity": float(similarity),
                "threshold": float(threshold),
                "assumption": "similarity ~= 1 - distance",
            }

        if chosen_existing is not None and similarity is not None and similarity >= threshold:
            # Merge path: use LLM merge prompt if available; fallback to heuristic.
            merged_content = content
            merged_extra: dict[str, Any] = dict(chosen_existing.extra or {})
            merge_used = False

            if not dry_run and llm is not None:
                merge_prompt = render_template(
                    cfg.reasoningbank.merge_prompt_template,
                    {
                        "existing_item_json": json.dumps(_memory_to_dict(chosen_existing), ensure_ascii=False, indent=2),
                        "new_item_json": json.dumps(proposal, ensure_ascii=False, indent=2),
                    },
                ).strip()
                system = _system_prompt(cfg)
                store.append_event(
                    rid,
                    "rb_llm_request",
                    {
                        "ts": time.time(),
                        "rb_job_id": rb_job_id,
                        "purpose": "merge",
                        "mem_id": chosen_existing.mem_id,
                        "model": getattr(llm, "model", None),
                        "base_url": getattr(llm, "base_url", None),
                        "temperature": 0.0,
                        "response_schema": "rb_merge_result",
                        "system": system,
                        "prompt": merge_prompt,
                    },
                )
                merge_extra: dict[str, Any] = {}
                if not bool(getattr(llm, "enable_thinking", False)):
                    merge_extra["response_format"] = _merge_response_format()
                try:
                    raw_merge = llm.chat_messages(
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": merge_prompt}],
                        temperature=0.0,
                        extra=merge_extra,
                    )
                except Exception as e:
                    store.append_event(
                        rid,
                        "rb_llm_response",
                        {
                            "ts": time.time(),
                            "rb_job_id": rb_job_id,
                            "purpose": "merge",
                            "mem_id": chosen_existing.mem_id,
                            "error": f"llm_call_failed_with_response_format: {e}",
                        },
                    )
                    raw_merge = llm.chat_messages(
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": merge_prompt}],
                        temperature=0.0,
                        extra={},
                    )
                store.append_event(
                    rid,
                    "rb_llm_response",
                    {
                        "ts": time.time(),
                        "rb_job_id": rb_job_id,
                        "purpose": "merge",
                        "mem_id": chosen_existing.mem_id,
                        "content": raw_merge.content,
                        "raw": raw_merge.raw,
                        "tool_calls": raw_merge.tool_calls,
                    },
                )
                try:
                    merged_obj = extract_first_json_object(raw_merge.content)
                    merged_content = str(merged_obj.get("content") or "").strip()
                    if not merged_content:
                        merged_content = content
                    if merged_content == "NOT_DUPLICATE":
                        merged_content = content
                    else:
                        merge_used = True
                    merged_extra.update(_ensure_dict(merged_obj.get("extra")))
                except JSONExtractionError:
                    merged_content = content

            if not merge_used:
                # Heuristic: keep the longer statement and record the proposal in extra for traceability.
                if len(chosen_existing.content.strip()) >= len(content):
                    merged_content = chosen_existing.content
                merged_extra = dict(chosen_existing.extra or {})
                merged_extra.setdefault("merged_from", []).append(
                    {
                        "source_run_id": rid,
                        "proposal": content,
                    }
                )

            before = chosen_existing
            after = rb.upsert(
                mem_id=chosen_existing.mem_id,
                status=chosen_existing.status,
                role=chosen_existing.role,
                type=chosen_existing.type,
                content=merged_content,
                source_run_id=chosen_existing.source_run_id,
                schema_version=chosen_existing.schema_version,
                extra=merged_extra,
                preserve_created_at=True,
            )
            _sync_rb_mem_index(store, after)

            store.append_mem_edit_log(
                mem_id=after.mem_id,
                actor="rb_learn",
                reason=f"learn_merge:{rb_job_id}",
                before=_memory_to_dict(before),
                after=_memory_to_dict(after),
                extra={"near_duplicate": dup_debug, "merge_used": bool(merge_used)},
            )

            ops.append(
                {
                    "op": "update",
                    "mem_id": after.mem_id,
                    "before": _memory_to_dict(before),
                    "after": _memory_to_dict(after),
                    "near_duplicate": dup_debug,
                    "merge_used": bool(merge_used),
                }
            )
            continue

        # Add as a new item (keep conflicts by default).
        after = rb.upsert(
            mem_id=None,
            status="active",
            role=role,
            type=typ,
            content=content,
            source_run_id=rid,
            schema_version=1,
            extra={
                **extra,
                "source_run_id": rid,
                "strategy_version": cfg.reasoningbank.strategy_version,
            },
            preserve_created_at=True,
        )
        _sync_rb_mem_index(store, after)

        store.append_mem_edit_log(
            mem_id=after.mem_id,
            actor="rb_learn",
            reason=f"learn_add:{rb_job_id}",
            before={},
            after=_memory_to_dict(after),
            extra={"near_duplicate_checked": dup_debug},
        )

        ops.append(
            {
                "op": "add",
                "mem_id": after.mem_id,
                "after": _memory_to_dict(after),
                "near_duplicate_checked": dup_debug,
            }
        )

    if not ops:
        # Still record an empty delta for auditability.
        ops = []

    delta = store.create_rb_delta(
        run_id=rid,
        ops=ops,
        schema_version=1,
        extra={
            "rb_job_id": rb_job_id,
            "strategy_version": cfg.reasoningbank.strategy_version,
            "dry_run": dry_run,
        },
    )

    store.append_event(
        rid,
        "rb_learn_completed",
        {"rb_job_id": rb_job_id, "delta_id": delta.delta_id, "n_ops": len(ops), "dry_run": dry_run},
    )
    return delta.delta_id


def safe_execute_rb_learn_job(
    store: SQLiteStore,
    *,
    rb: ReasoningBankStore,
    cfg: AppConfig,
    llm: OpenAICompatibleChatClient | None,
    run_id: str,
    rb_job_id: str,
) -> str | None:
    try:
        return learn_reasoningbank_for_run(
            store,
            rb=rb,
            cfg=cfg,
            llm=llm,
            run_id=run_id,
            rb_job_id=rb_job_id,
        )
    except Exception as e:
        store.append_event(
            run_id,
            "rb_learn_failed",
            {"rb_job_id": rb_job_id, "error": str(e), "traceback": traceback.format_exc()},
        )
        return None
