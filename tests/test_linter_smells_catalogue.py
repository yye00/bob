"""Tests for bob3.linter.smells_catalogue (F-R7-410 full 22-smell extension).

Verifies detect_all_smells and filter_by_severity behave correctly across
happy-path, boundary, and error scenarios.
"""

from __future__ import annotations

import pytest

from bob3.linter.smells_catalogue import (
    BLOCKING_SMELLS,
    SMELL_CATALOG,
    SmellFinding,
    blocks_plan_create,
    detect_all_smells,
    detector_count,
    filter_by_severity,
)


class TestDetectAllSmells:
    def test_returns_list(self):
        result = detect_all_smells("pytest: tests/test_foo.py")
        assert isinstance(result, list)

    def test_clean_ac_returns_empty(self):
        findings = detect_all_smells("pytest: tests/test_foo.py")
        assert findings == []

    def test_subjective_adjective_triggers_finding(self):
        findings = detect_all_smells("The system shall be fast.")
        assert len(findings) > 0

    def test_finding_has_required_attributes(self):
        findings = detect_all_smells("The system shall be fast.")
        assert len(findings) > 0
        f = findings[0]
        assert hasattr(f, "smell_id")
        assert hasattr(f, "severity")
        assert hasattr(f, "blocks_plan")
        assert hasattr(f, "detail")

    def test_e_severity_finding_blocks_plan(self):
        findings = detect_all_smells("The system shall be fast.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert all(f.blocks_plan for f in e_findings)

    def test_non_e_severity_does_not_block_plan(self):
        findings = detect_all_smells("The system shall work quickly.")
        w_findings = [f for f in findings if f.severity == "W"]
        assert all(not f.blocks_plan for f in w_findings)

    def test_loophole_triggers_e_severity(self):
        findings = detect_all_smells("The system shall process data if possible.")
        e_ids = {f.smell_id for f in findings if f.severity == "E"}
        assert "S03" in e_ids

    def test_empty_string_returns_empty(self):
        findings = detect_all_smells("")
        assert findings == []

    def test_whitespace_only_returns_empty_or_list(self):
        findings = detect_all_smells("   ")
        assert isinstance(findings, list)

    def test_peer_criteria_none_accepted(self):
        findings = detect_all_smells("pytest: tests/test_foo.py", peer_criteria=None)
        assert isinstance(findings, list)

    def test_peer_criteria_list_accepted(self):
        findings = detect_all_smells("File exists: src/foo.py", peer_criteria=["pytest: tests/test_foo.py"])
        assert isinstance(findings, list)

    def test_known_feature_ids_none_accepted(self):
        findings = detect_all_smells("pytest: tests/test_foo.py", known_feature_ids=None)
        assert isinstance(findings, list)

    def test_known_feature_ids_frozenset_accepted(self):
        findings = detect_all_smells("pytest: tests/test_foo.py", known_feature_ids=frozenset(["abc-123"]))
        assert isinstance(findings, list)

    def test_multiple_smells_detected_in_one_text(self):
        text = "The system shall be fast and simple if possible."
        findings = detect_all_smells(text)
        smell_ids = {f.smell_id for f in findings}
        assert len(smell_ids) >= 2

    def test_findings_ordered_by_smell_id(self):
        text = "The system shall be fast and simple if possible."
        findings = detect_all_smells(text)
        ids = [f.smell_id for f in findings]
        assert ids == sorted(ids)

    def test_raises_value_error_on_non_string(self):
        with pytest.raises(ValueError, match="detect_all_smells expects a str"):
            detect_all_smells(42)  # type: ignore[arg-type]

    def test_raises_value_error_on_none(self):
        with pytest.raises(ValueError):
            detect_all_smells(None)  # type: ignore[arg-type]

    def test_raises_value_error_on_list(self):
        with pytest.raises(ValueError):
            detect_all_smells(["some criterion"])  # type: ignore[arg-type]


class TestFilterBySeverity:
    def test_filter_e_returns_only_e(self):
        findings = detect_all_smells("The system shall be fast and simple if possible.")
        errors = filter_by_severity(findings, "E")
        assert all(f.severity == "E" for f in errors)

    def test_filter_w_returns_only_w(self):
        findings = detect_all_smells("The system shall work quickly.")
        warnings = filter_by_severity(findings, "W")
        assert all(f.severity == "W" for f in warnings)

    def test_filter_i_returns_only_i(self):
        findings = detect_all_smells("The system shall be fast.")
        infos = filter_by_severity(findings, "I")
        assert all(f.severity == "I" for f in infos)

    def test_filter_empty_list_returns_empty(self):
        result = filter_by_severity([], "E")
        assert result == []

    def test_filter_no_match_returns_empty(self):
        # Clean text produces no findings, so any filter returns []
        findings = detect_all_smells("pytest: tests/test_foo.py")
        result = filter_by_severity(findings, "E")
        assert result == []

    def test_filter_invalid_severity_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid severity"):
            filter_by_severity([], "X")  # type: ignore[arg-type]

    def test_filter_invalid_lowercase_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "e")  # type: ignore[arg-type]

    def test_filter_returns_list(self):
        findings = detect_all_smells("The system shall be fast.")
        result = filter_by_severity(findings, "E")
        assert isinstance(result, list)


class TestCatalogueMetadata:
    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_smell_catalog_has_22_entries(self):
        assert len(SMELL_CATALOG) == 22

    def test_blocking_smells_non_empty(self):
        assert len(BLOCKING_SMELLS) > 0

    def test_blocking_smells_all_e_severity(self):
        from bob3.linter.smells_catalogue import SMELL_BY_ID
        for smell_id in BLOCKING_SMELLS:
            defn = SMELL_BY_ID[smell_id]
            assert defn.severity == "E", f"{smell_id} in BLOCKING_SMELLS but severity={defn.severity}"


class TestBlocksPlanCreate:
    def test_no_findings_does_not_block(self):
        assert blocks_plan_create([]) is False

    def test_e_severity_blocks(self):
        findings = detect_all_smells("The system shall be fast.")
        e_findings = [f for f in findings if f.severity == "E"]
        if e_findings:
            assert blocks_plan_create(e_findings) is True

    def test_blocks_plan_create_with_clean_ac(self):
        findings = detect_all_smells("pytest: tests/test_foo.py")
        assert blocks_plan_create(findings) is False
