from __future__ import annotations

import json


_PREFERRED_KEY_SETS: list[set[str]] = [
    # ReCAP planner output
    {"think", "subtasks"},
    # ReCAP final output
    {"recipes"},
    # ReasoningBank extract/merge outputs
    {"items"},
    {"content"},
]


class JSONExtractionError(ValueError):
    pass


def extract_first_json_object(text: str) -> dict:
    """Extract and parse a JSON object from an LLM response.

    We prefer deterministic single-object JSON outputs, but many OpenAI-compatible
    gateways/models occasionally prepend/append extra text or emit multiple JSON
    objects. This helper is best-effort:
    - parse the first decodable object when the response is clean
    - tolerate extra text/code fences
    - when multiple objects are present, pick the most likely contract object
    """

    # Fast-path: handle the common case of a clean single JSON payload.
    s = (text or "").strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            # Fall through to the robust extractor below.
            pass

    # Robust extractor: scan for JSON objects and parse via JSONDecoder.raw_decode.
    # This tolerates extra text, code fences, and multiple concatenated JSON objects
    # (a common provider/gateway quirk).
    decoder = json.JSONDecoder()

    candidates: list[tuple[int, int, dict]] = []  # (start_idx, end_idx, obj)
    last_err: json.JSONDecodeError | None = None

    i = 0
    while True:
        i = text.find("{", i)
        if i == -1:
            break

        try:
            parsed, end = decoder.raw_decode(text[i:])
        except json.JSONDecodeError as e:
            last_err = e
            i += 1
            continue

        if isinstance(parsed, dict):
            candidates.append((i, i + end, parsed))
            # Skip nested objects inside this JSON payload.
            i = i + end
            continue

        i += 1

    if not candidates:
        if "{" not in (text or ""):
            raise JSONExtractionError("No JSON object found in response.")
        if last_err is not None:
            raise JSONExtractionError(f"Invalid JSON: {last_err}") from last_err
        raise JSONExtractionError("No JSON object found in response.")

    if len(candidates) == 1:
        return candidates[0][2]

    # If we found multiple objects, pick the one that most likely matches our
    # structured-output contracts.
    def _pick_best(matching: list[tuple[int, int, dict]]) -> dict:
        # Prefer larger payloads (likely top-level contract) and later ones when tied
        # (models often emit a corrected object after an initial attempt).
        start_idx, end_idx, obj = max(matching, key=lambda t: (t[1] - t[0], t[0]))
        _ = start_idx, end_idx
        return obj

    for keys in _PREFERRED_KEY_SETS:
        matching = [c for c in candidates if keys.issubset(set(c[2].keys()))]
        if matching:
            return _pick_best(matching)

    # Fallback: return the largest parsed object.
    return _pick_best(candidates)
