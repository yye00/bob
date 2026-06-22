"""Tests for bob3.linter_22_smells — the public 22-smell linter API.

Verifies that detect_smells wraps the 22-detector catalogue correctly,
that E-severity smells block plan --create, and that the module's public
symbols are all accessible.
"""

from __future__ import annotations

import pytest

from bob3.linter_22_smells import (
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

    def test_spacy_backed_detectors_callable(self):
        assert callable(spacy_backed_detectors)

    def test_handle_missing_spacy_model_callable(self):
        assert callable(handle_missing_spacy_model)

    def test_smell_catalog_available(self):
        assert SMELL_CATALOG is not None
        assert len(SMELL_CATALOG) == 22

    def test_smell_by_id_available(self):
        assert SMELL_BY_ID is not None
        assert len(SMELL_BY_ID) == 22

    def test_blocking_smells_available(self):
        assert BLOCKING_SMELLS is not None
        assert len(BLOCKING_SMELLS) > 0

    def test_spacy_smells_available(self):
        assert SPACY_SMELLS is not None
        assert len(SPACY_SMELLS) == 7

    def test_smell_finding_class_available(self):
        assert SmellFinding is not None

    def test_smell_definition_class_available(self):
        assert SmellDefinition is not None

    def test_spacy_model_missing_error_available(self):
        assert SpacyModelMissingError is not None


# ---------------------------------------------------------------------------
# detect_smells return type and structure
# ---------------------------------------------------------------------------

class TestDetectSmellsReturnType:
    def test_returns_list(self):
        result = detect_smells("The system shall be fast.")
        assert isinstance(result, list)

    def test_clean_text_returns_empty(self):
        # A structured, measurable criterion has no smells
        result = detect_smells("pytest: tests/test_foo.py -v")
        assert result == []

    def test_each_finding_is_smell_finding(self):
        result = detect_smells("The system shall be fast and simple.")
        for finding in result:
            assert isinstance(finding, SmellFinding)

    def test_finding_has_smell_id(self):
        result = detect_smells("The system shall be fast.")
        assert len(result) > 0
        for finding in result:
            assert hasattr(finding, "smell_id")
            assert finding.smell_id.startswith("S")

    def test_finding_has_severity(self):
        result = detect_smells("The system shall be fast.")
        assert len(result) > 0
        for finding in result:
            assert hasattr(finding, "severity")
            assert finding.severity in ("E", "W", "I")

    def test_finding_has_blocks_plan_property(self):
        result = detect_smells("The system shall be fast.")
        assert len(result) > 0
        for finding in result:
            assert hasattr(finding, "blocks_plan")

    def test_finding_has_detail(self):
        result = detect_smells("The system shall be fast.")
        assert len(result) > 0
        for finding in result:
            assert hasattr(finding, "detail")
            assert isinstance(finding.detail, str)

    def test_finding_has_text(self):
        text = "The system shall be fast."
        result = detect_smells(text)
        assert len(result) > 0
        for finding in result:
            assert finding.text == text


# ---------------------------------------------------------------------------
# E-severity smells block plan --create
# ---------------------------------------------------------------------------

class TestEseverityBlocksPlanCreate:
    def test_subjective_adjective_is_error(self):
        findings = detect_smells("The API shall be fast and reliable.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert len(e_findings) > 0, "Expected E-severity for subjective adjectives"

    def test_loophole_is_error(self):
        findings = detect_smells("The system shall respond if possible.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert len(e_findings) > 0, "Expected E-severity for loophole clause"

    def test_modal_weakness_is_error(self):
        findings = detect_smells("The system should return a result.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert len(e_findings) > 0, "Expected E-severity for modal weakness"

    def test_blocks_plan_create_true_for_error_findings(self):
        findings = detect_smells("The system shall be fast if possible.")
        assert blocks_plan_create(findings) is True

    def test_blocks_plan_create_false_for_no_error(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert blocks_plan_create(findings) is False

    def test_e_severity_finding_blocks_plan_property(self):
        findings = detect_smells("The system shall be fast.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert len(e_findings) > 0
        for f in e_findings:
            assert f.blocks_plan is True

    def test_w_severity_finding_does_not_block_plan(self):
        # S04 (open-ended-enumeration) is W severity
        findings = detect_smells("The system shall handle errors, etc.")
        w_findings = [f for f in findings if f.severity == "W" and f.smell_id == "S04"]
        if w_findings:
            for f in w_findings:
                assert f.blocks_plan is False


# ---------------------------------------------------------------------------
# Specific detector coverage
# ---------------------------------------------------------------------------

class TestSpecificDetectors:
    def test_s01_subjective_adjective_detected(self):
        findings = detect_smells("The UI shall be intuitive and clean.")
        smell_ids = [f.smell_id for f in findings]
        assert "S01" in smell_ids

    def test_s03_loophole_detected(self):
        findings = detect_smells("The system shall retry where applicable.")
        smell_ids = [f.smell_id for f in findings]
        assert "S03" in smell_ids

    def test_s04_open_ended_enumeration_detected(self):
        findings = detect_smells("The system shall support JSON, XML, etc.")
        smell_ids = [f.smell_id for f in findings]
        assert "S04" in smell_ids

    def test_s09_modal_weakness_detected(self):
        findings = detect_smells("The service should respond within 200ms.")
        smell_ids = [f.smell_id for f in findings]
        assert "S09" in smell_ids

    def test_s11_magic_number_detected(self):
        findings = detect_smells("The system shall retry 5 times.")
        smell_ids = [f.smell_id for f in findings]
        assert "S11" in smell_ids

    def test_s13_run_on_detected(self):
        text = "The system shall log all events and the system shall alert when threshold is exceeded."
        findings = detect_smells(text)
        smell_ids = [f.smell_id for f in findings]
        assert "S13" in smell_ids

    def test_s16_future_tense_detected(self):
        findings = detect_smells("The feature will be available next release.")
        smell_ids = [f.smell_id for f in findings]
        assert "S16" in smell_ids

    def test_s22_behavior_without_pytest_detected(self):
        behavior_ac = "behavior: when the user submits, the form saves"
        other_criteria = ["File exists: src/foo.py"]
        findings = detect_smells(behavior_ac, peer_criteria=other_criteria)
        smell_ids = [f.smell_id for f in findings]
        assert "S22" in smell_ids

    def test_s22_not_triggered_when_pytest_peer_exists(self):
        behavior_ac = "behavior: when the user submits, the form saves"
        other_criteria = ["pytest: tests/test_form.py -v"]
        findings = detect_smells(behavior_ac, peer_criteria=other_criteria)
        smell_ids = [f.smell_id for f in findings]
        assert "S22" not in smell_ids

    def test_s17_dangling_feature_id_detected(self):
        text = "The system shall implement behavior as described in F-R7-999."
        known_ids = frozenset({"F-R7-001", "F-R7-002"})
        findings = detect_smells(text, known_feature_ids=known_ids)
        smell_ids = [f.smell_id for f in findings]
        assert "S17" in smell_ids

    def test_s17_not_triggered_for_known_id(self):
        text = "The system shall implement behavior as described in F-R7-001."
        known_ids = frozenset({"F-R7-001"})
        findings = detect_smells(text, known_feature_ids=known_ids)
        s17 = [f for f in findings if f.smell_id == "S17"]
        assert len(s17) == 0


# ---------------------------------------------------------------------------
# Catalogue metadata helpers
# ---------------------------------------------------------------------------

class TestCatalogueHelpers:
    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_spacy_backed_detectors_count_is_7(self):
        backed = spacy_backed_detectors()
        assert len(backed) == 7

    def test_spacy_backed_detectors_correct_ids(self):
        backed = set(spacy_backed_detectors())
        assert backed == {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}

    def test_severity_of_s01_is_e(self):
        assert severity_of("S01") == "E"

    def test_severity_of_s02_is_w(self):
        assert severity_of("S02") == "W"

    def test_severity_of_s15_is_i(self):
        assert severity_of("S15") == "I"

    def test_severity_of_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown severity"):
            severity_of("S99")

    def test_is_blocking_e_severity(self):
        assert is_blocking("S01") is True

    def test_is_blocking_w_severity_is_false(self):
        assert is_blocking("S02") is False

    def test_handle_missing_spacy_model_raises(self):
        with pytest.raises(SpacyModelMissingError, match="en_core_web_sm"):
            handle_missing_spacy_model()

    def test_blocking_smells_are_all_e_severity(self):
        for smell_id in BLOCKING_SMELLS:
            assert SMELL_BY_ID[smell_id].severity == "E"

    def test_spacy_smells_uses_spacy_true(self):
        for smell_id in SPACY_SMELLS:
            assert SMELL_BY_ID[smell_id].uses_spacy is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string_returns_empty(self):
        result = detect_smells("")
        assert result == []

    def test_whitespace_only_returns_empty(self):
        result = detect_smells("   ")
        assert result == []

    def test_none_peer_criteria_no_crash(self):
        result = detect_smells("The system shall be fast.", peer_criteria=None)
        assert isinstance(result, list)

    def test_none_known_feature_ids_no_crash(self):
        result = detect_smells("See F-R7-999 for details.", known_feature_ids=None)
        assert isinstance(result, list)

    def test_multiple_smells_in_one_criterion(self):
        text = "The system should be fast and simple if possible, etc."
        findings = detect_smells(text)
        assert len(findings) >= 3

    def test_clean_pytest_criterion(self):
        result = detect_smells("pytest: tests/test_linter_22_smells.py -v")
        assert result == []

    def test_clean_file_exists_criterion(self):
        result = detect_smells("File exists: src/bob3/linter_22_smells.py")
        assert result == []
