"""Tests for bob.synthesizer.parse_criteria_response.

Covers:
- Flat JSON array of strings (nominal case)
- Object-format LLM output with various key names
- Mixed arrays
- Missing/malformed JSON
- Empty arrays
"""
import pytest
from bob_legacy.synthesizer import parse_criteria_response


def test_flat_string_array():
    response = '```json\n["File exists: src/foo.py", "pytest: tests/test_foo.py"]\n```'
    result = parse_criteria_response(response)
    assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]


def test_object_format_criterion_key():
    response = '```json\n[{"criterion": "File exists: src/foo.py"}, {"criterion": "pytest: tests/test_foo.py"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]


def test_object_format_ac_key():
    response = '```json\n[{"ac": "File exists: src/bar.py"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["File exists: src/bar.py"]


def test_object_format_acceptance_criterion_key():
    response = '```json\n[{"acceptance_criterion": "Function defined: bob.foo.bar"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["Function defined: bob.foo.bar"]


def test_object_format_text_key():
    response = '```json\n[{"text": "pytest: tests/test_baz.py"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["pytest: tests/test_baz.py"]


def test_object_format_description_key():
    response = '```json\n[{"id": 1, "description": "File exists: src/thing.py"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["File exists: src/thing.py"]


def test_object_format_value_key():
    response = '```json\n[{"value": "integration: bob.orchestrator"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["integration: bob.orchestrator"]


def test_mixed_objects_and_strings():
    response = '```json\n[{"criterion": "File exists: src/foo.py"}, "pytest: tests/test_foo.py"]\n```'
    result = parse_criteria_response(response)
    assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]


def test_object_with_id_and_criterion():
    """Realistic LLM output with id + criterion + description fields."""
    response = (
        '```json\n'
        '[{"id":1,"criterion":"File exists: src/bob/synthesizer.py","description":"source file"},'
        '{"id":2,"criterion":"pytest: tests/test_synthesizer.py","description":"tests"}]\n'
        '```'
    )
    result = parse_criteria_response(response)
    assert result == [
        "File exists: src/bob/synthesizer.py",
        "pytest: tests/test_synthesizer.py",
    ]


def test_no_fenced_block_falls_back_to_inline():
    response = 'Here are the ACs: ["File exists: src/foo.py", "pytest: tests/test_foo.py"]'
    result = parse_criteria_response(response)
    assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]


def test_empty_array_returns_none():
    response = '```json\n[]\n```'
    result = parse_criteria_response(response)
    assert result is None


def test_malformed_json_returns_none():
    response = '```json\n[not valid json\n```'
    result = parse_criteria_response(response)
    assert result is None


def test_no_json_at_all_returns_none():
    response = "Here are some acceptance criteria: blah blah blah."
    result = parse_criteria_response(response)
    assert result is None


def test_object_missing_known_keys_drops_entry():
    """Objects with no recognized text key are dropped, not str(dict)-coerced."""
    response = '```json\n[{"unknown_key": "something"}, {"criterion": "pytest: tests/test_x.py"}]\n```'
    result = parse_criteria_response(response)
    assert result == ["pytest: tests/test_x.py"]


def test_all_objects_missing_known_keys_returns_none():
    response = '```json\n[{"unknown": "val1"}, {"other": "val2"}]\n```'
    result = parse_criteria_response(response)
    assert result is None
