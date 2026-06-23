"""Tests that lint_spec raises ValueError with 'malformed' for invalid YAML input."""

from __future__ import annotations

import pytest

from bob3.spec_quality.ambiguity_linter import lint_spec


class TestInvalidYAMLErrorPath:
    def test_malformed_yaml_raises_value_error(self):
        malformed_yaml = ":: this is not valid yaml ::\n  - broken: [unclosed"
        with pytest.raises(ValueError, match="malformed"):
            lint_spec(malformed_yaml)

    def test_error_message_contains_malformed(self):
        malformed_yaml = ": bad: [unclosed bracket"
        with pytest.raises(ValueError) as exc_info:
            lint_spec(malformed_yaml)
        assert "malformed" in str(exc_info.value).lower()

    def test_non_list_yaml_raises_value_error(self):
        # Valid YAML but not a list — should raise ValueError with "malformed".
        yaml_str = "key: value\nnested: true"
        with pytest.raises(ValueError, match="malformed"):
            lint_spec(yaml_str)

    def test_empty_yaml_raises_value_error(self):
        # Empty YAML parses to None — should raise ValueError.
        with pytest.raises(ValueError, match="malformed"):
            lint_spec("")

    def test_yaml_string_with_valid_features_is_accepted(self):
        valid_yaml = """
- name: MyFeature
  acceptance_criteria:
    - "File exists: src/bob3/foo.py"
    - "pytest: tests/test_foo.py"
"""
        report = lint_spec(valid_yaml)
        assert report.passed

    def test_yaml_string_with_vague_ac_fails_lint(self):
        yaml_str = """
- name: VagueFeature
  acceptance_criteria:
    - "works correctly"
"""
        report = lint_spec(yaml_str)
        assert not report.passed
        assert report.failed_features[0].feature_name == "VagueFeature"

    def test_list_input_not_treated_as_yaml(self):
        # Passing a proper list should still work normally (no YAML parsing).
        features = [{"name": "F", "acceptance_criteria": ["pytest: tests/test_x.py"]}]
        report = lint_spec(features)
        assert report.passed

    def test_tab_indented_yaml_raises_value_error(self):
        # YAML forbids tabs for indentation — this should trigger a YAML parse error.
        malformed_yaml = "- name: Feature\n\tacceptance_criteria:\n\t\t- works"
        with pytest.raises(ValueError, match="malformed"):
            lint_spec(malformed_yaml)
