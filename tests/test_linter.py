"""Tests for bob.linter — public 22-smell linter entry point.

Verifies that detect_smells at bob.linter correctly wraps the 22-detector
catalogue, that E-severity smells block plan --create, and all public symbols
are accessible.
"""

from __future__ import annotations

import pytest

from bob.linter import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_smells,
    detector_count,
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

    def test_blocks_plan_create_callable(self):
        assert callable(blocks_plan_create)

    def test_severity_of_callable(self):
        assert callable(severity_of)

    def test_is_blocking_callable(self):
        assert callable(is_blocking)

    def test_detector_count_callable(self):
        assert callable(detector_count)

    def test_smell_catalog_has_22_entries(self):
        assert len(SMELL_CATALOG) == 22

    def test_smell_by_id_has_22_entries(self):
        assert len(SMELL_BY_ID) == 22

    def test_blocking_smells_non_empty(self):
        assert len(BLOCKING_SMELLS) > 0

    def test_spacy_smells_count_7(self):
        assert len(SPACY_SMELLS) == 7

    def test_spacy_backed_detectors_7(self):
        assert len(spacy_backed_detectors()) == 7

    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_smell_finding_class_accessible(self):
        assert SmellFinding is not None

    def test_smell_definition_class_accessible(self):
        assert SmellDefinition is not None

    def test_spacy_model_missing_error_accessible(self):
        assert SpacyModelMissingError is not None

    def test_handle_missing_spacy_model_raises(self):
        with pytest.raises(SpacyModelMissingError, match="en_core_web_sm"):
            handle_missing_spacy_model()


# ---------------------------------------------------------------------------
# detect_smells core behavior
# ---------------------------------------------------------------------------

class TestDetectSmells:
    def test_clean_structured_ac_no_findings(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert findings == []

    def test_subjective_adjective_blocks_plan(self):
        findings = detect_smells("The system shall be fast and reliable.")
        assert any(f.blocks_plan for f in findings)

    def test_loophole_blocks_plan(self):
        findings = detect_smells("The system shall respond if possible.")
        assert any(f.blocks_plan for f in findings)

    def test_modal_weakness_blocks_plan(self):
        findings = detect_smells("The system should return a result.")
        assert any(f.blocks_plan for f in findings)

    def test_returns_smell_finding_instances(self):
        findings = detect_smells("The system shall be fast.")
        assert all(isinstance(f, SmellFinding) for f in findings)

    def test_findings_ordered_by_smell_id(self):
        findings = detect_smells("The system should be fast and simple if possible, etc.")
        ids = [f.smell_id for f in findings]
        assert ids == sorted(ids)

    def test_file_exists_ac_clean(self):
        findings = detect_smells("File exists: src/bob/linter.py")
        assert not any(f.blocks_plan for f in findings)

    def test_peer_criteria_forwarded_s22(self):
        behavior_ac = "behavior: when user submits, form is saved"
        findings = detect_smells(behavior_ac, peer_criteria=["File exists: src/foo.py"])
        smell_ids = [f.smell_id for f in findings]
        assert "S22" in smell_ids

    def test_pytest_peer_suppresses_s22(self):
        behavior_ac = "behavior: when user submits, form is saved"
        findings = detect_smells(
            behavior_ac, peer_criteria=["pytest: tests/test_form.py -v"]
        )
        smell_ids = [f.smell_id for f in findings]
        assert "S22" not in smell_ids

    def test_known_feature_ids_forwarded_s17(self):
        text = "See F-R7-999 for behavior details."
        findings = detect_smells(text, known_feature_ids=frozenset({"F-R7-001"}))
        smell_ids = [f.smell_id for f in findings]
        assert "S17" in smell_ids


# ---------------------------------------------------------------------------
# Severity / blocking helpers
# ---------------------------------------------------------------------------

class TestSeverityHelpers:
    def test_severity_of_s01_is_e(self):
        assert severity_of("S01") == "E"

    def test_severity_of_s02_is_w(self):
        assert severity_of("S02") == "W"

    def test_severity_of_s15_is_i(self):
        assert severity_of("S15") == "I"

    def test_severity_of_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("S99")

    def test_is_blocking_e_severity(self):
        assert is_blocking("S01") is True

    def test_is_blocking_w_severity(self):
        assert is_blocking("S02") is False

    def test_blocks_plan_create_with_e_finding(self):
        findings = detect_smells("The system shall be fast.")
        assert blocks_plan_create(findings) is True

    def test_blocks_plan_create_empty_list(self):
        assert blocks_plan_create([]) is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string_no_crash(self):
        findings = detect_smells("")
        assert findings == []

    def test_whitespace_only_no_crash(self):
        findings = detect_smells("   ")
        assert isinstance(findings, list)

    def test_none_peer_criteria_no_crash(self):
        findings = detect_smells("The system shall be fast.", peer_criteria=None)
        assert isinstance(findings, list)

    def test_none_known_feature_ids_no_crash(self):
        findings = detect_smells("See F-R7-999.", known_feature_ids=None)
        assert isinstance(findings, list)
