from __future__ import annotations

import pytest

from src.utils.json_extract import JSONExtractionError, extract_first_json_object


def test_extract_first_json_object_parses_clean_json() -> None:
    assert extract_first_json_object('{"a": 1}') == {"a": 1}


def test_extract_first_json_object_tolerates_trailing_text() -> None:
    text = '{"a": 1}\n\n(extra text that should be ignored)'
    assert extract_first_json_object(text) == {"a": 1}


def test_extract_first_json_object_selects_contract_object_when_multiple_present() -> (
    None
):
    # Simulate gateways that concatenate multiple assistant messages.
    text = '{"foo": 1}{"think": "t", "subtasks": [], "result": ""}'
    obj = extract_first_json_object(text)
    assert obj.get("think") == "t"
    assert obj.get("subtasks") == []


def test_extract_first_json_object_ignores_example_object_before_contract() -> None:
    text = 'Example: {"foo": 1}\n{"think": "t", "subtasks": [], "result": "r"}'
    obj = extract_first_json_object(text)
    assert obj.get("result") == "r"


def test_extract_first_json_object_supports_array_wrapped_object() -> None:
    # Some models wrap the object in a single-element array.
    text = '[{"think": "t", "subtasks": [], "result": "r"}]'
    obj = extract_first_json_object(text)
    assert obj.get("think") == "t"


def test_extract_first_json_object_raises_when_no_object_present() -> None:
    with pytest.raises(JSONExtractionError):
        extract_first_json_object("no json here")
