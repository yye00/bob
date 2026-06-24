"""Tests for bob.smell_linter_22 — Full 22-smell linter extension (F-R7-410).

Covers detect_all_smells and filter_by_severity.
E-severity findings block bob plan --create.
"""

from __future__ import annotations

import pytest

from bob.smell_linter_22 import (
    SmellFinding,
    blocks_plan_create,
    detect_all_smells,
    filter_by_severity,
)


class TestDetectAllSmells:
    def test_returns_list(self):
        result = detect_all_smells("pytest: tests/test_foo.py")
        assert isinstance(result, list)

    def test_clean_ac_returns_empty(self):
        result = detect_all_smells("pytest: tests/test_foo.py")
        assert result == []

    def test_subjective_adjective_triggers_e_severity(self):
        result = detect_all_smells("The system shall be fast and reliable.")
        assert any(f.severity == "E" for f in result)

    def test_findings_have_expected_attributes(self):
        result = detect_all_smells("The system shall be fast.")
        assert len(result) > 0
        finding = result[0]
        assert isinstance(finding, SmellFinding)
        assert finding.smell_id.startswith("S")
        assert finding.severity in {"E", "W", "I"}
        assert isinstance(finding.text, str)
        assert isinstance(finding.detail, str)

    def test_blocks_plan_property_set_for_error_severity(self):
        result = detect_all_smells("The system shall be fast.")
        error_findings = [f for f in result if f.severity == "E"]
        assert all(f.blocks_plan for f in error_findings)

    def test_empty_string_returns_empty(self):
        result = detect_all_smells("")
        assert result == []

    def test_non_str_input_raises_value_error(self):
        with pytest.raises(ValueError, match="detect_all_smells expects a str"):
            detect_all_smells(123)  # type: ignore[arg-type]

    def test_non_str_none_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_all_smells(None)  # type: ignore[arg-type]

    def test_loophole_detected(self):
        result = detect_all_smells("The system shall respond quickly if possible.")
        smell_ids = {f.smell_id for f in result}
        assert "S03" in smell_ids

    def test_peer_criteria_accepted(self):
        result = detect_all_smells("pytest: tests/test_foo.py", peer_criteria=["other: AC"])
        assert isinstance(result, list)

    def test_known_feature_ids_accepted(self):
        result = detect_all_smells("pytest: tests/test_foo.py", known_feature_ids=frozenset({"F-001"}))
        assert isinstance(result, list)

    def test_all_findings_have_valid_severity(self):
        result = detect_all_smells("The system shall be fast, simple, and easy.")
        for f in result:
            assert f.severity in {"E", "W", "I"}


class TestFilterBySeverity:
    def test_filter_errors_from_mixed(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        errors = filter_by_severity(findings, "E")
        assert all(f.severity == "E" for f in errors)

    def test_filter_warnings(self):
        findings = detect_all_smells("The system shall respond quickly.")
        warnings = filter_by_severity(findings, "W")
        assert all(f.severity == "W" for f in warnings)

    def test_filter_informational(self):
        findings = detect_all_smells("pytest: tests/test_foo.py")
        infos = filter_by_severity(findings, "I")
        assert isinstance(infos, list)

    def test_filter_empty_list_returns_empty(self):
        result = filter_by_severity([], "E")
        assert result == []

    def test_invalid_severity_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "X")

    def test_invalid_severity_lowercase_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "e")

    def test_filter_e_is_subset_of_all_findings(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        errors = filter_by_severity(findings, "E")
        assert set(id(f) for f in errors).issubset(set(id(f) for f in findings))


class TestBlocksPlanCreate:
    def test_e_severity_blocks_plan(self):
        findings = detect_all_smells("The system shall be fast.")
        assert blocks_plan_create(findings) is True

    def test_clean_ac_does_not_block(self):
        findings = detect_all_smells("pytest: tests/test_foo.py")
        assert blocks_plan_create(findings) is False

    def test_empty_findings_does_not_block(self):
        assert blocks_plan_create([]) is False


class TestIntegrationWithPatterns:
    """Verify bob.patterns can import from bob.smell_linter_22."""

    def test_smell_linter_22_importable_from_bob(self):
        import bob.smell_linter_22 as module
        assert hasattr(module, "detect_all_smells")
        assert hasattr(module, "filter_by_severity")

    def test_detect_all_smells_callable(self):
        from bob.smell_linter_22 import detect_all_smells
        assert callable(detect_all_smells)

    def test_filter_by_severity_callable(self):
        from bob.smell_linter_22 import filter_by_severity
        assert callable(filter_by_severity)
