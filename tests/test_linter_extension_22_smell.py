"""Tests for bob.linter_extension_22_smell (feature 8a8802cf).

Covers: detect_smells, validate_severity, and integration with bob.plan gating.
"""

from __future__ import annotations

import pytest

from bob.linter_extension_22_smell import (
    BLOCKING_SMELLS,
    SMELL_CATALOG,
    SmellFinding,
    SmellSeverity,
    blocks_plan_create,
    detect_smells,
    detector_count,
    filter_by_severity,
    validate_severity,
)


# ---------------------------------------------------------------------------
# detect_smells — basic behaviour
# ---------------------------------------------------------------------------

class TestDetectSmells:
    def test_returns_list(self):
        result = detect_smells("pytest: tests/test_foo.py -v")
        assert isinstance(result, list)

    def test_clean_ac_returns_empty(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert findings == []

    def test_subjective_adjective_triggers_error(self):
        findings = detect_smells("The system shall be fast.")
        assert any(f.smell_id == "S01" for f in findings)
        assert any(f.severity == "E" for f in findings)

    def test_loophole_triggers_error(self):
        findings = detect_smells("The system shall handle requests if possible.")
        assert any(f.smell_id == "S03" for f in findings)

    def test_open_ended_enum_triggers_warning(self):
        findings = detect_smells("The system shall support JSON, XML, etc.")
        assert any(f.smell_id == "S04" for f in findings)

    def test_multiple_smells_in_one_text(self):
        findings = detect_smells("The system shall be fast and simple, etc.")
        smell_ids = {f.smell_id for f in findings}
        # Should detect S01 (subjective adjective) and S04 (open-ended)
        assert len(smell_ids) >= 2

    def test_each_finding_has_required_fields(self):
        findings = detect_smells("The system shall be fast.")
        for f in findings:
            assert isinstance(f.smell_id, str)
            assert isinstance(f.smell_name, str)
            assert f.severity in ("E", "W", "I")
            assert isinstance(f.text, str)
            assert isinstance(f.detail, str)

    def test_blocks_plan_property_true_for_e_severity(self):
        findings = detect_smells("The system shall be fast.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert all(f.blocks_plan for f in e_findings)

    def test_blocks_plan_false_for_warning(self):
        findings = detect_smells("The system shall respond quickly.")
        w_findings = [f for f in findings if f.severity == "W"]
        assert all(not f.blocks_plan for f in w_findings)

    def test_non_string_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a str"):
            detect_smells(None)  # type: ignore[arg-type]

    def test_integer_input_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a str"):
            detect_smells(42)  # type: ignore[arg-type]

    def test_peer_criteria_accepted(self):
        findings = detect_smells(
            "behavior: the system logs the event",
            peer_criteria=["pytest: tests/test_logging.py"],
        )
        assert isinstance(findings, list)

    def test_known_feature_ids_accepted(self):
        findings = detect_smells(
            "See feature F-R7-001.",
            known_feature_ids=frozenset({"F-R7-001"}),
        )
        assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# validate_severity
# ---------------------------------------------------------------------------

class TestValidateSeverity:
    @pytest.mark.parametrize("sev", ["E", "W", "I"])
    def test_valid_severities_return_same(self, sev):
        assert validate_severity(sev) == sev

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid severity"):
            validate_severity("X")

    def test_lowercase_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid severity"):
            validate_severity("e")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid severity"):
            validate_severity("")

    def test_error_message_lists_valid_options(self):
        with pytest.raises(ValueError) as exc_info:
            validate_severity("Z")
        msg = str(exc_info.value)
        assert "E" in msg
        assert "W" in msg
        assert "I" in msg


# ---------------------------------------------------------------------------
# filter_by_severity
# ---------------------------------------------------------------------------

class TestFilterBySeverity:
    def test_filter_errors_only(self):
        findings = detect_smells("The system shall be fast and simple.")
        errors = filter_by_severity(findings, "E")
        assert all(f.severity == "E" for f in errors)

    def test_filter_warnings_only(self):
        findings = detect_smells("The system shall respond quickly.")
        warnings = filter_by_severity(findings, "W")
        assert all(f.severity == "W" for f in warnings)

    def test_filter_with_invalid_severity_raises(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "X")


# ---------------------------------------------------------------------------
# blocks_plan_create integration
# ---------------------------------------------------------------------------

class TestBlocksPlanCreate:
    def test_e_severity_blocks(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert blocks_plan_create(findings) is True

    def test_clean_ac_does_not_block(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert blocks_plan_create(findings) is False

    def test_empty_findings_does_not_block(self):
        assert blocks_plan_create([]) is False


# ---------------------------------------------------------------------------
# Catalogue integrity
# ---------------------------------------------------------------------------

class TestCatalogueIntegrity:
    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_smell_catalog_has_22_entries(self):
        assert len(SMELL_CATALOG) == 22

    def test_all_smell_ids_unique(self):
        ids = [s.id for s in SMELL_CATALOG]
        assert len(ids) == len(set(ids))

    def test_blocking_smells_subset_of_catalog(self):
        catalog_ids = {s.id for s in SMELL_CATALOG}
        for sid in BLOCKING_SMELLS:
            assert sid in catalog_ids

    def test_all_severities_valid(self):
        for smell in SMELL_CATALOG:
            assert smell.severity in ("E", "W", "I")
