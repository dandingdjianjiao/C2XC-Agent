from __future__ import annotations

import json


class JSONExtractionError(ValueError):
    pass


def extract_first_json_object(text: str) -> dict:
    """Extract and parse the first JSON object from an LLM response.

    This is intentionally strict: we want the model to output JSON deterministically.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise JSONExtractionError("No JSON object found in response.")

    candidate = text[start : end + 1].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise JSONExtractionError(f"Invalid JSON: {e}") from e

