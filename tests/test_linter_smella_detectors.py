"""Tests for bob3.linter.smella_detectors.detect_all_smells.

Verifies the smella_detectors module provides the full 22-detector
catalogue with correct severity semantics and the detect_all_smells
entry point.
"""

from __future__ import annotations

import pytest

from bob3.linter.smella_detectors import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    SpacyModelMissingError,
    blocks_plan_create,
    detect_all_smells,
    detector_count,
    handle_missing_spacy_model,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)


# ---------------------------------------------------------------------------
# Module-level exports are present
# ---------------------------------------------------------------------------

class TestModuleExports:
    def test_detect_all_smells_is_callable(self):
        assert callable(detect_all_smells)

    def test_blocks_plan_create_is_callable(self):
        assert callable(blocks_plan_create)

    def test_detector_count_is_callable(self):
        assert callable(detector_count)

    def test_severity_of_is_callable(self):
        assert callable(severity_of)

    def test_is_blocking_is_callable(self):
        assert callable(is_blocking)

    def test_spacy_backed_detectors_is_callable(self):
        assert callable(spacy_backed_detectors)

    def test_smell_catalog_is_list(self):
        assert isinstance(SMELL_CATALOG, (list, tuple, frozenset, set)) or hasattr(
            SMELL_CATALOG, "__iter__"
        )

    def test_blocking_smells_is_collection(self):
        assert hasattr(BLOCKING_SMELLS, "__contains__")

    def test_spacy_smells_is_collection(self):
        assert hasattr(SPACY_SMELLS, "__contains__")


# ---------------------------------------------------------------------------
# detector_count returns 22
# ---------------------------------------------------------------------------

class TestDetectorCount:
    def test_22_detectors(self):
        assert detector_count() == 22

    def test_7_spacy_backed_detectors(self):
        assert len(spacy_backed_detectors()) == 7

    def test_spacy_backed_ids_known(self):
        backed = spacy_backed_detectors()
        for sid in backed:
            assert sid.startswith("S"), f"Unexpected smell ID: {sid}"


# ---------------------------------------------------------------------------
# detect_all_smells — happy path
# ---------------------------------------------------------------------------

class TestDetectAllSmellsHappyPath:
    def test_clean_ac_returns_empty_list(self):
        findings = detect_all_smells("pytest: tests/test_foo.py")
        assert findings == []

    def test_returns_list(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        assert isinstance(findings, list)

    def test_smelly_text_returns_findings(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        assert len(findings) > 0

    def test_findings_are_smell_finding_instances(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        for f in findings:
            assert isinstance(f, SmellFinding)

    def test_e_severity_blocks_plan(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        e_findings = [f for f in findings if f.severity == "E"]
        if e_findings:
            assert all(f.blocks_plan for f in e_findings)

    def test_w_severity_does_not_block_plan(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        w_findings = [f for f in findings if f.severity == "W"]
        assert all(not f.blocks_plan for f in w_findings)

    def test_i_severity_does_not_block_plan(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        i_findings = [f for f in findings if f.severity == "I"]
        assert all(not f.blocks_plan for f in i_findings)

    def test_finding_has_smell_id(self):
        findings = detect_all_smells("The system shall be fast.")
        for f in findings:
            assert hasattr(f, "smell_id")
            assert isinstance(f.smell_id, str)

    def test_finding_has_detail(self):
        findings = detect_all_smells("The system shall be fast.")
        for f in findings:
            assert hasattr(f, "detail")
            assert isinstance(f.detail, str)

    def test_blocks_plan_create_true_for_e_severity(self):
        findings = detect_all_smells("The system shall be fast and simple.")
        any_e = any(f.severity == "E" for f in findings)
        if any_e:
            assert blocks_plan_create(findings) is True

    def test_blocks_plan_create_false_for_clean(self):
        findings = detect_all_smells("pytest: tests/test_foo.py")
        assert blocks_plan_create(findings) is False

    def test_ordered_by_smell_id(self):
        findings = detect_all_smells("The system shall be fast and complex and simple.")
        ids = [f.smell_id for f in findings]
        assert ids == sorted(ids)

    def test_peer_criteria_accepted(self):
        findings = detect_all_smells(
            "behavior: WHEN the user logs in THEN the system responds",
            peer_criteria=["pytest: tests/test_login.py"],
        )
        assert isinstance(findings, list)

    def test_known_feature_ids_accepted(self):
        findings = detect_all_smells(
            "pytest: tests/test_foo.py",
            known_feature_ids=frozenset(["F-R7-001", "F-R7-002"]),
        )
        assert isinstance(findings, list)

    def test_all_params_provided(self):
        findings = detect_all_smells(
            "The system shall handle requests fast.",
            peer_criteria=["pytest: tests/test_req.py"],
            known_feature_ids=frozenset(["F-R7-410"]),
        )
        assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# detect_all_smells — error path
# ---------------------------------------------------------------------------

class TestDetectAllSmellsErrors:
    def test_non_str_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_all_smells(123)  # type: ignore[arg-type]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_all_smells(None)  # type: ignore[arg-type]

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_all_smells(["some", "text"])  # type: ignore[arg-type]

    def test_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_all_smells(b"bytes input")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

class TestSeverityHelpers:
    def test_severity_of_known_blocking_smell(self):
        # S01 is a blocking E-severity smell
        if "S01" in SMELL_BY_ID:
            sev = severity_of("S01")
            assert sev == "E"

    def test_is_blocking_for_blocking_smell(self):
        for sid in BLOCKING_SMELLS:
            assert is_blocking(sid) is True

    def test_is_blocking_false_for_non_blocking(self):
        # S04 is not a blocking smell
        if "S04" in SMELL_BY_ID and "S04" not in BLOCKING_SMELLS:
            assert is_blocking("S04") is False

    def test_blocks_plan_create_on_empty_list(self):
        assert blocks_plan_create([]) is False
