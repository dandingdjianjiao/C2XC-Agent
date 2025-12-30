from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KBSearchAction:
    kb_name: str
    query: str
    top_k: int | None = None
    mode: str | None = None


@dataclass(frozen=True)
class KBGetAction:
    """Fetch a previously retrieved KB chunk by its short alias (e.g. C12).

    This is a *local* operation: it reads from the per-run evidence registry
    accumulated by prior kb_search calls, not from LightRAG.
    """

    alias: str


@dataclass(frozen=True)
class KBListAction:
    """List KB evidence already retrieved in this run.

    This is a *local* operation: it reads from the per-run evidence registry
    accumulated by prior kb_search calls, not from LightRAG.
    """

    limit: int | None = None


@dataclass(frozen=True)
class GenerateRecipesAction:
    pass


PrimitiveAction = KBSearchAction | KBGetAction | KBListAction | GenerateRecipesAction


_KB_SEARCH_RE = re.compile(
    r'^kb_search\s+(?P<kb>[a-zA-Z0-9_]+)\s+"(?P<query>[^"]+)"(?P<rest>.*)$'
)
# Alias like C1 or KB12, optionally wrapped in [].
_KB_GET_RE = re.compile(r"^kb_get\s+(?P<alias>\[?[A-Z]+\d+\]?)\s*$")
_KB_LIST_RE = re.compile(r"^kb_list(?P<rest>.*)$")
_BRACKET_ARG_RE = re.compile(r"\[(?P<key>[a-zA-Z_]+)=(?P<value>[^\]]+)\]")


def parse_primitive_action(text: str) -> PrimitiveAction | None:
    """Parse a primitive action subtask.

    Supported syntax (must match system prompt):
      - kb_search <kb_name> "<query>" [top_k=<int>] [mode=<...>]
      - kb_get <alias>
      - kb_list [limit=<int>]
      - generate_recipes
    """
    s = (text or "").strip()
    if not s:
        return None
    if s == "generate_recipes":
        return GenerateRecipesAction()

    m_get = _KB_GET_RE.match(s)
    if m_get:
        alias = m_get.group("alias").strip()
        if alias.startswith("[") and alias.endswith("]"):
            alias = alias[1:-1].strip()
        return KBGetAction(alias=alias)

    m_list = _KB_LIST_RE.match(s)
    if m_list:
        rest = (m_list.group("rest") or "").strip()
        kwargs: dict[str, str] = {}
        for am in _BRACKET_ARG_RE.finditer(rest):
            kwargs[am.group("key").strip()] = am.group("value").strip()
        limit: int | None = None
        if "limit" in kwargs:
            try:
                limit = int(kwargs["limit"])
            except Exception:
                limit = None
        return KBListAction(limit=limit)

    m = _KB_SEARCH_RE.match(s)
    if not m:
        return None

    kb_name = m.group("kb").strip()
    query = m.group("query").strip()
    rest = (m.group("rest") or "").strip()

    kwargs: dict[str, str] = {}
    for am in _BRACKET_ARG_RE.finditer(rest):
        kwargs[am.group("key").strip()] = am.group("value").strip()

    top_k: int | None = None
    if "top_k" in kwargs:
        try:
            top_k = int(kwargs["top_k"])
        except Exception:
            top_k = None

    mode = kwargs.get("mode")
    if mode is not None:
        mode = mode.strip()

    return KBSearchAction(kb_name=kb_name, query=query, top_k=top_k, mode=mode)


def strip_role_prefix(task: str) -> tuple[str, str]:
    """Map prefixed composite tasks to a role.

    - "MOF: ..." -> role="mof_expert"
    - "TIO2: ..." -> role="tio2_expert"
    - otherwise -> role="orchestrator" (default)
    """
    s = (task or "").strip()
    upper = s.upper()
    if upper.startswith("MOF:"):
        return "mof_expert", s[4:].strip()
    if upper.startswith("TIO2:"):
        return "tio2_expert", s[5:].strip()
    return "orchestrator", s
