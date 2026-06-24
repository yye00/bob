"""Tests for bob.linter_22_smell — the public 22-smell linter API (F-R7-410 extension).

Verifies that detect_smells and filter_by_severity work correctly through
the bob.linter_22_smell module name (with underscore between 22 and smell).
"""

from __future__ import annotations

import pytest

from bob.linter_22_smell import (
    BLOCKING_SMELLS,
    SMELL_CATALOG,
    SMELL_BY_ID,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_smells,
    detector_count,
    filter_by_severity,
    handle_missing_spacy_model,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)


# ---------------------------------------------------------------------------
# Module-level symbol availability
# ---------------------------------------------------------------------------

class TestPublicSymbols:
    def test_detect_smells_callable(self):
        assert callable(detect_smells)

    def test_filter_by_severity_callable(self):
        assert callable(filter_by_severity)

    def test_blocks_plan_create_callable(self):
        assert callable(blocks_plan_create)

    def test_severity_of_callable(self):
        assert callable(severity_of)

    def test_is_blocking_callable(self):
        assert callable(is_blocking)

    def test_detector_count_callable(self):
        assert callable(detector_count)

    def test_spacy_backed_detectors_callable(self):
        assert callable(spacy_backed_detectors)

    def test_handle_missing_spacy_model_callable(self):
        assert callable(handle_missing_spacy_model)

    def test_smell_catalog_has_22_entries(self):
        assert SMELL_CATALOG is not None
        assert len(SMELL_CATALOG) == 22

    def test_smell_by_id_has_22_entries(self):
        assert SMELL_BY_ID is not None
        assert len(SMELL_BY_ID) == 22

    def test_blocking_smells_non_empty(self):
        assert BLOCKING_SMELLS is not None
        assert len(BLOCKING_SMELLS) > 0

    def test_spacy_smells_count(self):
        assert SPACY_SMELLS is not None
        assert len(SPACY_SMELLS) == 7

    def test_smell_finding_class_available(self):
        assert SmellFinding is not None

    def test_smell_definition_class_available(self):
        assert SmellDefinition is not None

    def test_spacy_model_missing_error_available(self):
        assert SpacyModelMissingError is not None


# ---------------------------------------------------------------------------
# detect_smells functional tests
# ---------------------------------------------------------------------------

class TestDetectSmells:
    def test_returns_list(self):
        findings = detect_smells("The system shall be fast.")
        assert isinstance(findings, list)

    def test_vague_shall_triggers_finding(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert len(findings) > 0

    def test_clean_pytest_ac_returns_empty(self):
        findings = detect_smells("pytest: tests/test_foo.py")
        assert findings == []

    def test_finding_has_severity_attribute(self):
        findings = detect_smells("The system shall be fast and reliable.")
        for f in findings:
            assert hasattr(f, "severity")
            assert f.severity in {"E", "W", "I"}

    def test_finding_has_blocks_plan_attribute(self):
        findings = detect_smells("The system shall be fast and reliable.")
        for f in findings:
            assert hasattr(f, "blocks_plan")
            assert isinstance(f.blocks_plan, bool)

    def test_blocks_plan_create_on_vague_input(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert blocks_plan_create(findings) is True

    def test_no_blocks_plan_on_clean_input(self):
        findings = detect_smells("pytest: tests/test_foo.py")
        assert blocks_plan_create(findings) is False

    def test_peer_criteria_accepted(self):
        findings = detect_smells(
            "behavior: system processes request when input is valid",
            peer_criteria=["pytest: tests/test_behavior.py"],
        )
        assert isinstance(findings, list)

    def test_known_feature_ids_accepted(self):
        findings = detect_smells(
            "File exists: src/bob/foo.py",
            known_feature_ids=frozenset(["F-R7-001"]),
        )
        assert isinstance(findings, list)

    def test_empty_string_returns_empty(self):
        findings = detect_smells("")
        assert findings == []

    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_spacy_backed_count_is_7(self):
        assert len(spacy_backed_detectors()) == 7


# ---------------------------------------------------------------------------
# filter_by_severity tests
# ---------------------------------------------------------------------------

class TestFilterBySeverity:
    def test_filter_errors_only(self):
        findings = detect_smells("The system shall be fast and simple.")
        errors = filter_by_severity(findings, "E")
        assert all(f.severity == "E" for f in errors)

    def test_filter_warnings_only(self):
        findings = detect_smells("The system shall be fast and simple.")
        warnings = filter_by_severity(findings, "W")
        assert all(f.severity == "W" for f in warnings)

    def test_filter_info_only(self):
        findings = detect_smells("The system shall be fast and simple.")
        infos = filter_by_severity(findings, "I")
        assert all(f.severity == "I" for f in infos)

    def test_filter_empty_list_returns_empty(self):
        result = filter_by_severity([], "E")
        assert result == []

    def test_filter_invalid_severity_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "X")

    def test_filter_invalid_severity_lowercase_raises(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "e")

    def test_filter_severity_partitions_findings(self):
        findings = detect_smells("The system shall be fast and simple and reliable.")
        errors = filter_by_severity(findings, "E")
        warnings = filter_by_severity(findings, "W")
        infos = filter_by_severity(findings, "I")
        all_filtered = errors + warnings + infos
        assert len(all_filtered) == len(findings)
