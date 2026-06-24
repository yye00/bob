"""Tests for parse_criteria_response handling object-format LLM output.

Root cause: the LLM frequently returns a list of OBJECTS like
[{"id":1,"criterion":"...","description":"..."}]. str(dict) yields a
Python-repr string that is not a machine-verifiable AC. These tests verify
that parse_criteria_response correctly extracts criterion text from objects.
"""
from __future__ import annotations

import json

import pytest
from bob.synthesizer import parse_criteria_response


class TestParseCriteriaResponseObjectFormat:
    """parse_criteria_response must handle object-format LLM responses."""

    def test_flat_string_array_parses_correctly(self):
        """Baseline: flat JSON array of strings returns list of strings."""
        payload = json.dumps(["pytest: tests/test_x.py", "File exists: src/foo.py"])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert "pytest: tests/test_x.py" in result
        assert "File exists: src/foo.py" in result

    def test_object_array_with_criterion_key(self):
        """Object list with 'criterion' key: extract criterion text, not repr."""
        payload = json.dumps([
            {"id": 1, "criterion": "pytest: tests/test_a.py", "description": "run tests"},
            {"id": 2, "criterion": "File exists: src/bar.py", "description": "file check"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert len(result) == 2
        assert "pytest: tests/test_a.py" in result
        assert "File exists: src/bar.py" in result
        for item in result:
            assert not item.startswith("{"), f"Should not be dict repr: {item!r}"

    def test_object_array_with_ac_key(self):
        """Object list with 'ac' key extracts value."""
        payload = json.dumps([
            {"ac": "Function defined: bob.synthesizer.parse_criteria_response"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert result[0] == "Function defined: bob.synthesizer.parse_criteria_response"

    def test_object_array_with_acceptance_criterion_key(self):
        """Object list with 'acceptance_criterion' key extracts value."""
        payload = json.dumps([
            {"acceptance_criterion": "integration: bob.orchestrator"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert result[0] == "integration: bob.orchestrator"

    def test_object_array_with_text_key(self):
        """Object list with 'text' key extracts value."""
        payload = json.dumps([
            {"text": "pytest: tests/test_boundary.py"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert result[0] == "pytest: tests/test_boundary.py"

    def test_object_array_with_description_key(self):
        """Object list with 'description' key used as fallback."""
        payload = json.dumps([
            {"description": "pytest: tests/test_desc.py"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert result[0] == "pytest: tests/test_desc.py"

    def test_mixed_string_and_object_array(self):
        """Mixed array of strings and objects: both are extracted."""
        payload = json.dumps([
            "File exists: src/foo.py",
            {"criterion": "pytest: tests/test_foo.py"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert "File exists: src/foo.py" in result
        assert "pytest: tests/test_foo.py" in result

    def test_object_with_no_known_key_is_excluded(self):
        """Objects with no recognized key produce empty string, excluded from result."""
        payload = json.dumps([
            {"unknown_key": "something"},
            {"criterion": "pytest: tests/test_good.py"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        # Unknown-key object is excluded; good object is included
        assert "pytest: tests/test_good.py" in result
        for item in result:
            assert "unknown_key" not in item

    def test_result_contains_no_dict_reprs(self):
        """No item in result should look like a Python dict repr."""
        payload = json.dumps([
            {"id": 1, "criterion": "pytest: tests/test_x.py"},
            {"id": 2, "ac": "File exists: src/x.py"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert result is not None
        for item in result:
            assert not item.startswith("{'") and not item.startswith('{"'), (
                f"Item looks like a dict repr: {item!r}"
            )

    def test_empty_json_array_returns_none(self):
        """Empty JSON array returns None (no criteria to use)."""
        result = parse_criteria_response("```json\n[]\n```")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        result = parse_criteria_response("")
        assert result is None

    def test_no_json_block_returns_none(self):
        """Text without a JSON block returns None."""
        result = parse_criteria_response("Here are some criteria: use tests.")
        assert result is None

    def test_null_json_returns_none(self):
        """JSON null returns None."""
        result = parse_criteria_response("```json\nnull\n```")
        assert result is None

    def test_object_array_with_value_key(self):
        """Object list with 'value' key extracts value."""
        payload = json.dumps([{"value": "pytest: tests/test_val.py"}])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert result[0] == "pytest: tests/test_val.py"

    def test_criterion_key_takes_priority_over_description(self):
        """'criterion' key has priority over 'description' key."""
        payload = json.dumps([
            {"criterion": "pytest: tests/test_priority.py", "description": "other text"},
        ])
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert result[0] == "pytest: tests/test_priority.py"

    def test_seven_ac_object_format_all_extracted(self):
        """Full 7-AC object-format response (typical LLM output) extracts all 7."""
        acs = [
            {"id": i + 1, "criterion": f"AC-{i+1}: some criterion", "description": "..."}
            for i in range(7)
        ]
        payload = json.dumps(acs)
        result = parse_criteria_response(f"```json\n{payload}\n```")
        assert isinstance(result, list)
        assert len(result) == 7
        for i, item in enumerate(result):
            assert item == f"AC-{i+1}: some criterion"
