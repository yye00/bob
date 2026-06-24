"""Tests for bob.linters.smella_22 — the 22-smell linter in the linters subpackage.

Verifies that detect_smells wraps the 22-detector catalogue correctly,
that E-severity smells block plan --create, and that the module's public
symbols are all accessible via bob.linters.smella_22.
"""

from __future__ import annotations

import pytest

from bob.linters.smella_22 import (
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

    def test_smell_catalog_has_22_entries(self):
        assert len(SMELL_CATALOG) == 22

    def test_smell_by_id_has_22_entries(self):
        assert len(SMELL_BY_ID) == 22

    def test_blocking_smells_non_empty(self):
        assert len(BLOCKING_SMELLS) > 0

    def test_spacy_smells_has_7_entries(self):
        assert len(SPACY_SMELLS) == 7

    def test_smell_finding_class_available(self):
        assert SmellFinding is not None

    def test_smell_definition_class_available(self):
        assert SmellDefinition is not None

    def test_spacy_model_missing_error_available(self):
        assert SpacyModelMissingError is not None


# ---------------------------------------------------------------------------
# detect_smells behaviour
# ---------------------------------------------------------------------------

class TestDetectSmells:
    def test_subjective_adjective_detected(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert len(findings) > 0
        assert any(f.smell_id == "S01" for f in findings)

    def test_clean_ac_returns_empty(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert findings == []

    def test_returns_list_of_smell_finding(self):
        findings = detect_smells("The system should be easy.")
        assert isinstance(findings, list)
        for f in findings:
            assert isinstance(f, SmellFinding)

    def test_finding_has_severity(self):
        findings = detect_smells("The system shall be fast.")
        assert len(findings) > 0
        for f in findings:
            assert f.severity in ("E", "W", "I")

    def test_finding_blocks_plan_property(self):
        findings = detect_smells("The system shall be fast.")
        for f in findings:
            assert isinstance(f.blocks_plan, bool)
            assert f.blocks_plan == (f.severity == "E")

    def test_empty_string_returns_empty_list(self):
        findings = detect_smells("")
        assert findings == []

    def test_none_peer_criteria_no_crash(self):
        findings = detect_smells("The system shall respond.", peer_criteria=None)
        assert isinstance(findings, list)

    def test_empty_peer_criteria_no_crash(self):
        findings = detect_smells("behavior: when user logs in", peer_criteria=[])
        assert isinstance(findings, list)

    def test_none_known_feature_ids_no_crash(self):
        findings = detect_smells("The system shall respond.", known_feature_ids=None)
        assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# blocks_plan_create integration
# ---------------------------------------------------------------------------

class TestBlocksPlanCreate:
    def test_error_severity_blocks_plan(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert blocks_plan_create(findings) is True

    def test_clean_text_does_not_block_plan(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert blocks_plan_create(findings) is False

    def test_empty_findings_does_not_block(self):
        assert blocks_plan_create([]) is False


# ---------------------------------------------------------------------------
# Catalogue metadata
# ---------------------------------------------------------------------------

class TestCatalogueMetadata:
    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_spacy_backed_detectors_count(self):
        backed = spacy_backed_detectors()
        assert len(backed) == 7

    def test_spacy_backed_detectors_are_s01_s02_s05_s06_s07_s08_s18(self):
        backed = set(spacy_backed_detectors())
        assert backed == {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}

    def test_severity_of_known_smell(self):
        sev = severity_of("S01")
        assert sev == "E"

    def test_severity_of_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("S99")

    def test_is_blocking_true_for_error_smell(self):
        assert is_blocking("S01") is True

    def test_is_blocking_false_for_warning_smell(self):
        assert is_blocking("S02") is False

    def test_handle_missing_spacy_model_raises(self):
        with pytest.raises(SpacyModelMissingError):
            handle_missing_spacy_model()
