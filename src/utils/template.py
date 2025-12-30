from __future__ import annotations

import re
from typing import Any


_VAR_RE = re.compile(r"\{\{\s*(?P<key>[a-zA-Z0-9_]+)\s*\}\}")


def render_template(template: str, variables: dict[str, Any]) -> str:
    """Very small template renderer compatible with the ReCAP repo's {{var}} style."""

    def _replace(match: re.Match[str]) -> str:
        key = match.group("key")
        value = variables.get(key, "")
        return str(value)

    return _VAR_RE.sub(_replace, template)

