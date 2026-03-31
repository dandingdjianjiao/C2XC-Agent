from __future__ import annotations

import math
import re
from typing import Any


_RATIO_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
_WS_RE = re.compile(r"\s+")
_DISPLAY_COOH_SUFFIX_RE = re.compile(r"\s*\(\s*-cooh\s*\)\s*$", re.IGNORECASE)


def _normalize_space(value: Any) -> str:
    return _WS_RE.sub(" ", str(value or "").strip())


def normalize_metal(value: Any) -> str:
    return _normalize_space(value).upper()


def normalize_atomic_ratio(value: Any) -> str:
    raw = _normalize_space(value)
    m = _RATIO_RE.match(raw)
    if m is None:
        return raw

    left = int(m.group(1))
    right = int(m.group(2))
    if left <= 0 or right <= 0:
        return raw

    g = math.gcd(left, right)
    return f"{left // g}:{right // g}"


def normalize_modifier(value: Any) -> str:
    raw = _normalize_space(value).lower()
    if not raw:
        return raw
    return _DISPLAY_COOH_SUFFIX_RE.sub("", raw).strip()


def canonicalize_recipe(recipe: dict[str, Any]) -> dict[str, str]:
    return {
        "M1": normalize_metal(recipe.get("M1")),
        "M2": normalize_metal(recipe.get("M2")),
        "atomic_ratio": normalize_atomic_ratio(recipe.get("atomic_ratio")),
        "small_molecule_modifier": normalize_modifier(recipe.get("small_molecule_modifier")),
    }


def canonical_recipe_key(recipe: dict[str, Any]) -> str:
    norm = canonicalize_recipe(recipe)
    return (
        f"M1={norm['M1']}|"
        f"M2={norm['M2']}|"
        f"atomic_ratio={norm['atomic_ratio']}|"
        f"small_molecule_modifier={norm['small_molecule_modifier']}"
    )


def recipe_brief(recipe: dict[str, Any]) -> str:
    m1 = _normalize_space(recipe.get("M1"))
    m2 = _normalize_space(recipe.get("M2"))
    ratio = _normalize_space(recipe.get("atomic_ratio"))
    modifier = _normalize_space(recipe.get("small_molecule_modifier"))
    return (
        f"M1={m1 or '?'}; "
        f"M2={m2 or '?'}; "
        f"atomic_ratio={ratio or '?'}; "
        f"small_molecule_modifier={modifier or '?'}"
    )
