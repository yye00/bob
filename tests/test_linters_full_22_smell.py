"""Tests for bob.linters.full_22_smell — Full 22-smell linter extension to F-R7-410.

Verifies that detect_smells is accessible from the bob.linters.full_22_smell
namespace and behaves correctly with E/W/I severities, spaCy-backed detectors,
and the blocks_plan_create gate.
"""

from __future__ import annotations

import pytest

from bob.linters.full_22_smell import (
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


class TestDetectSmellsBasics:
    def test_returns_list(self):
        result = detect_smells("The system shall be fast.")
        assert isinstance(result, list)

    def test_clean_ac_returns_empty(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert findings == []

    def test_vague_ac_returns_findings(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert len(findings) > 0

    def test_findings_are_smell_finding_instances(self):
        findings = detect_smells("The system shall be fast.")
        for finding in findings:
            assert isinstance(finding, SmellFinding)

    def test_findings_have_severity(self):
        findings = detect_smells("The system shall be fast.")
        for finding in findings:
            assert finding.severity in ("E", "W", "I")

    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_e_severity_blocks_plan(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert blocks_plan_create(findings) is True

    def test_clean_text_does_not_block(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert blocks_plan_create(findings) is False


class TestSmellCatalog:
    def test_catalog_has_22_entries(self):
        assert len(SMELL_CATALOG) == 22

    def test_by_id_has_22_entries(self):
        assert len(SMELL_BY_ID) == 22

    def test_blocking_smells_non_empty(self):
        assert len(BLOCKING_SMELLS) > 0

    def test_spacy_smells_count_7(self):
        assert len(SPACY_SMELLS) == 7

    def test_spacy_smells_ids(self):
        assert set(SPACY_SMELLS) == {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}

    def test_severity_of_s01_is_e(self):
        assert severity_of("S01") == "E"

    def test_is_blocking_s01(self):
        assert is_blocking("S01") is True

    def test_spacy_backed_detectors_count(self):
        assert len(spacy_backed_detectors()) == 7


class TestOptionalParameters:
    def test_peer_criteria_accepted(self):
        findings = detect_smells(
            "behavior: when submitted, the form saves",
            peer_criteria=["pytest: tests/test_form.py -v"],
        )
        smell_ids = [f.smell_id for f in findings]
        assert "S22" not in smell_ids

    def test_peer_criteria_none_no_crash(self):
        findings = detect_smells("The system shall be fast.", peer_criteria=None)
        assert isinstance(findings, list)

    def test_known_feature_ids_accepted(self):
        findings = detect_smells(
            "See F-R7-999 for details.",
            known_feature_ids=frozenset({"F-R7-001"}),
        )
        assert isinstance(findings, list)

    def test_known_feature_ids_none_no_crash(self):
        findings = detect_smells("See F-R7-999.", known_feature_ids=None)
        assert isinstance(findings, list)


class TestSpacyIntegration:
    def test_handle_missing_spacy_model_raises(self):
        with pytest.raises(SpacyModelMissingError, match="en_core_web_sm"):
            handle_missing_spacy_model()

    def test_spacy_model_missing_error_is_exception(self):
        assert issubclass(SpacyModelMissingError, Exception)


class TestSymbolExports:
    def test_detect_smells_callable(self):
        assert callable(detect_smells)

    def test_blocks_plan_create_callable(self):
        assert callable(blocks_plan_create)

    def test_smell_finding_accessible(self):
        assert SmellFinding is not None

    def test_smell_definition_accessible(self):
        assert SmellDefinition is not None

    def test_smell_severity_accessible(self):
        assert SmellSeverity is not None

    def test_spacy_model_missing_error_accessible(self):
        assert SpacyModelMissingError is not None
