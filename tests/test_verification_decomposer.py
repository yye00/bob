"""Tests for VerificationDecomposer's _parse_tests function."""

import pytest
from bob.orchestrator.decomposers.verification_decomposer import _parse_tests


class TestParseTests:
    def test_clean_json(self):
        output = '{"numerical_tests": [{"name": "t1", "command": "echo hi", "timeout": 30}], "algorithmic_tests": [], "convergence_tests": []}'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 1
        assert result["numerical_tests"][0]["name"] == "t1"

    def test_markdown_fences(self):
        output = '```json\n{"numerical_tests": [{"name": "t1", "command": "echo hi"}], "algorithmic_tests": [], "convergence_tests": []}\n```'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 1

    def test_commentary_around_json(self):
        output = 'Here are the tests:\n\n{"numerical_tests": [{"name": "t1", "command": "echo hi"}], "algorithmic_tests": [], "convergence_tests": []}\n\nThese tests cover...'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 1

    def test_missing_name_auto_generates(self):
        output = '{"numerical_tests": [{"command": "echo hi", "timeout": 30}], "algorithmic_tests": [], "convergence_tests": []}'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 1
        assert result["numerical_tests"][0]["name"] == "numerical_tests_0"

    def test_alternative_field_names(self):
        output = '{"numerical_tests": [{"title": "my test", "cmd": "echo hi"}], "algorithmic_tests": [], "convergence_tests": []}'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 1
        assert result["numerical_tests"][0]["name"] == "my test"
        assert result["numerical_tests"][0]["command"] == "echo hi"

    def test_empty_output(self):
        result = _parse_tests("")
        assert all(len(result[k]) == 0 for k in result)

    def test_no_command_skipped(self):
        output = '{"numerical_tests": [{"name": "bad_test"}], "algorithmic_tests": [], "convergence_tests": []}'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 0

    def test_all_categories(self):
        output = '{"numerical_tests": [{"name": "n1", "command": "a"}], "algorithmic_tests": [{"name": "a1", "command": "b"}], "convergence_tests": [{"name": "c1", "command": "c"}]}'
        result = _parse_tests(output)
        assert len(result["numerical_tests"]) == 1
        assert len(result["algorithmic_tests"]) == 1
        assert len(result["convergence_tests"]) == 1
