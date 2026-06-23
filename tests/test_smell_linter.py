"""Tests for bob3.smell_linter — the public lint_spec_for_smells entry point.

Verifies the 22-detector catalogue integration: clean inputs return empty
findings, smelly inputs return structured results, severities are classified,
and the function raises ValueError on non-string input.
"""

from __future__ import annotations

import pytest

from bob3.smell_linter import lint_spec_for_smells, SmellFinding, detector_count


class TestLintSpecForSmellsReturnShape:
    def test_returns_dict_with_required_keys(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert isinstance(result, dict)
        for key in (
            "findings",
            "blocks_plan_create",
            "error_count",
            "warning_count",
            "info_count",
            "detector_count",
            "spacy_backed",
        ):
            assert key in result, f"missing key {key!r}"

    def test_findings_is_list(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert isinstance(result["findings"], list)

    def test_blocks_plan_create_is_bool(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert isinstance(result["blocks_plan_create"], bool)

    def test_counts_are_ints(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert isinstance(result["error_count"], int)
        assert isinstance(result["warning_count"], int)
        assert isinstance(result["info_count"], int)

    def test_detector_count_is_22(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert result["detector_count"] == 22

    def test_spacy_backed_is_list(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert isinstance(result["spacy_backed"], list)


class TestCleanInput:
    def test_pytest_ac_is_clean(self):
        result = lint_spec_for_smells("pytest: tests/test_foo.py")
        assert result["findings"] == []
        assert result["blocks_plan_create"] is False
        assert result["error_count"] == 0

    def test_file_exists_ac_is_clean(self):
        result = lint_spec_for_smells("File exists: src/bob3/foo.py")
        assert isinstance(result["findings"], list)
        assert result["blocks_plan_create"] is False


class TestSmellyInput:
    def test_vague_shall_triggers_findings(self):
        result = lint_spec_for_smells("The system shall be fast and simple.")
        assert isinstance(result["findings"], list)
        assert len(result["findings"]) > 0

    def test_vague_ac_blocks_plan_create(self):
        result = lint_spec_for_smells("The system shall be fast and simple.")
        assert result["blocks_plan_create"] is True

    def test_error_count_positive_for_vague_ac(self):
        result = lint_spec_for_smells("The system shall be fast and simple.")
        assert result["error_count"] > 0

    def test_counts_sum_to_total_findings(self):
        result = lint_spec_for_smells("The system shall be fast and simple.")
        total = result["error_count"] + result["warning_count"] + result["info_count"]
        assert total == len(result["findings"])

    def test_findings_are_smell_findings(self):
        result = lint_spec_for_smells("The system shall be fast and simple.")
        for finding in result["findings"]:
            assert isinstance(finding, SmellFinding)

    def test_finding_has_severity_attribute(self):
        result = lint_spec_for_smells("The system shall be fast and simple.")
        for finding in result["findings"]:
            assert finding.severity in ("E", "W", "I")


class TestInvalidInput:
    def test_non_string_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_spec_for_smells(None)  # type: ignore[arg-type]

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_spec_for_smells(42)  # type: ignore[arg-type]

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_spec_for_smells(["pytest: tests/foo.py"])  # type: ignore[arg-type]


class TestOptionalArgs:
    def test_peer_criteria_accepted(self):
        result = lint_spec_for_smells(
            "behavior: WHEN user logs in THEN session is created",
            peer_criteria=["pytest: tests/test_auth.py"],
        )
        assert isinstance(result, dict)

    def test_known_feature_ids_accepted(self):
        result = lint_spec_for_smells(
            "See F-R7-410 for details",
            known_feature_ids=frozenset(["F-R7-410"]),
        )
        assert isinstance(result, dict)

    def test_none_args_accepted(self):
        result = lint_spec_for_smells(
            "pytest: tests/test_foo.py",
            peer_criteria=None,
            known_feature_ids=None,
        )
        assert isinstance(result, dict)


class TestBoundaryViaSmellLinter:
    def test_empty_string_returns_clean(self):
        result = lint_spec_for_smells("")
        assert result["findings"] == []
        assert result["blocks_plan_create"] is False

    def test_whitespace_only_no_crash(self):
        result = lint_spec_for_smells("   ")
        assert isinstance(result["findings"], list)

    def test_unicode_no_crash(self):
        result = lint_spec_for_smells("日本語テスト")
        assert isinstance(result["findings"], list)
