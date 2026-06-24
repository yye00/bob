"""Tests for synthesizer.parse_criteria.extract_criteria_from_response.

Covers object-format LLM output parsing (the historical root cause of
synthesized=0/118 across bob66-70) and flat-string format.
"""
import pytest
from synthesizer.parse_criteria import extract_criteria_from_response


class TestFlatStringFormat:
    def test_fenced_json_flat_strings(self):
        response = '```json\n["pytest: tests/test_foo.py", "File exists: src/foo.py"]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["pytest: tests/test_foo.py", "File exists: src/foo.py"]

    def test_bare_inline_json_array(self):
        response = 'Some text. ["pytest: tests/test_foo.py"] more text.'
        result = extract_criteria_from_response(response)
        assert result == ["pytest: tests/test_foo.py"]

    def test_single_string_element(self):
        result = extract_criteria_from_response('```json\n["File exists: src/bar.py"]\n```')
        assert result == ["File exists: src/bar.py"]

    def test_whitespace_stripped_from_strings(self):
        result = extract_criteria_from_response('```json\n["  File exists: src/foo.py  "]\n```')
        assert result == ["File exists: src/foo.py"]

    def test_empty_strings_are_dropped(self):
        result = extract_criteria_from_response('```json\n["", "File exists: src/foo.py", ""]\n```')
        assert result == ["File exists: src/foo.py"]


class TestObjectFormat:
    def test_criterion_key(self):
        response = '```json\n[{"id": 1, "criterion": "pytest: tests/test_x.py"}]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["pytest: tests/test_x.py"]

    def test_ac_key(self):
        response = '```json\n[{"ac": "File exists: src/module.py"}]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["File exists: src/module.py"]

    def test_acceptance_criterion_key(self):
        response = '```json\n[{"acceptance_criterion": "Function defined: module.func"}]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["Function defined: module.func"]

    def test_text_key(self):
        response = '```json\n[{"text": "File exists: src/x.py"}]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["File exists: src/x.py"]

    def test_description_key_fallback(self):
        response = '```json\n[{"description": "File exists: src/desc.py"}]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["File exists: src/desc.py"]

    def test_mixed_object_and_string(self):
        response = '```json\n[{"criterion": "File exists: src/a.py"}, "pytest: tests/test_b.py"]\n```'
        result = extract_criteria_from_response(response)
        assert "File exists: src/a.py" in result
        assert "pytest: tests/test_b.py" in result
        assert len(result) == 2

    def test_object_with_id_and_description(self):
        """Typical LLM output: {"id":1,"criterion":"...","description":"..."}"""
        response = '```json\n[{"id": 1, "criterion": "pytest: tests/test_foo.py", "description": "Runs the test"}]\n```'
        result = extract_criteria_from_response(response)
        # criterion key takes priority over description
        assert result == ["pytest: tests/test_foo.py"]

    def test_objects_without_known_keys_are_dropped(self):
        response = '```json\n[{"unknown_key": "pytest: tests/x.py"}, "File exists: src/y.py"]\n```'
        result = extract_criteria_from_response(response)
        assert result == ["File exists: src/y.py"]


class TestFailureCases:
    def test_empty_string_returns_none(self):
        assert extract_criteria_from_response("") is None

    def test_no_json_returns_none(self):
        assert extract_criteria_from_response("no json here") is None

    def test_empty_array_returns_none(self):
        assert extract_criteria_from_response('```json\n[]\n```') is None

    def test_null_json_returns_none(self):
        assert extract_criteria_from_response('```json\nnull\n```') is None

    def test_malformed_json_returns_none(self):
        assert extract_criteria_from_response('```json\n[not valid json\n```') is None

    def test_non_string_input_returns_none(self):
        assert extract_criteria_from_response(None) is None  # type: ignore[arg-type]

    def test_integer_input_returns_none(self):
        assert extract_criteria_from_response(42) is None  # type: ignore[arg-type]

    def test_all_elements_empty_objects_returns_none(self):
        response = '```json\n[{"unknown": "value"}, {"also_unknown": "val"}]\n```'
        result = extract_criteria_from_response(response)
        assert result is None
