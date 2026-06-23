"""Tests for full_22_smell_linter_extension_f_r7_410.

Verifies the extended linter entry point returns the expected structured
result dict and correctly gates bob3 plan --create on E-severity smells.
"""

from __future__ import annotations

import pytest

from bob3.full_22_smell_linter_extension_f_r7_410 import (
    full_22_smell_linter_extension_f_r7_410,
    detect_smells,
    SmellFinding,
    SmellDefinition,
    SmellSeverity,
    SMELL_CATALOG,
    SMELL_BY_ID,
    BLOCKING_SMELLS,
    SPACY_SMELLS,
    blocks_plan_create,
    severity_of,
    is_blocking,
    detector_count,
    spacy_backed_detectors,
    SpacyModelMissingError,
    handle_missing_spacy_model,
)


# ---------------------------------------------------------------------------
# Primary entry point: function exists and is callable
# ---------------------------------------------------------------------------

def test_full_22_smell_linter_extension_f_r7_410():
    """Primary AC test: function exists, is callable, and returns structured result."""
    result = full_22_smell_linter_extension_f_r7_410(
        "The system shall be fast and simple."
    )

    # Result is a dict with the expected keys
    assert isinstance(result, dict)
    assert "findings" in result
    assert "blocks_plan_create" in result
    assert "error_count" in result
    assert "warning_count" in result
    assert "info_count" in result
    assert "detector_count" in result
    assert "spacy_backed" in result

    # E-severity smells present — blocks plan --create
    assert result["blocks_plan_create"] is True
    assert result["error_count"] > 0

    # Always 22 detectors
    assert result["detector_count"] == 22

    # 7 spaCy-backed detectors
    assert len(result["spacy_backed"]) == 7

    # Findings are SmellFinding instances
    assert isinstance(result["findings"], list)
    for finding in result["findings"]:
        assert isinstance(finding, SmellFinding)


# ---------------------------------------------------------------------------
# Return structure completeness
# ---------------------------------------------------------------------------

class TestReturnStructure:
    def test_clean_text_blocks_plan_false(self):
        result = full_22_smell_linter_extension_f_r7_410("pytest: tests/test_foo.py -v")
        assert result["blocks_plan_create"] is False
        assert result["findings"] == []
        assert result["error_count"] == 0
        assert result["warning_count"] == 0
        assert result["info_count"] == 0

    def test_error_count_matches_findings(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The system shall be fast if possible."
        )
        e_count = sum(1 for f in result["findings"] if f.severity == "E")
        assert result["error_count"] == e_count

    def test_warning_count_matches_findings(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The system shall handle errors, etc."
        )
        w_count = sum(1 for f in result["findings"] if f.severity == "W")
        assert result["warning_count"] == w_count

    def test_info_count_matches_findings(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The system shall function correctly."
        )
        i_count = sum(1 for f in result["findings"] if f.severity == "I")
        assert result["info_count"] == i_count

    def test_detector_count_always_22(self):
        for text in [
            "pytest: tests/test_foo.py -v",
            "The system shall be fast.",
            "",
        ]:
            result = full_22_smell_linter_extension_f_r7_410(text)
            assert result["detector_count"] == 22

    def test_spacy_backed_correct_ids(self):
        result = full_22_smell_linter_extension_f_r7_410("The system shall be fast.")
        assert set(result["spacy_backed"]) == {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}


# ---------------------------------------------------------------------------
# Severity / blocking behaviour
# ---------------------------------------------------------------------------

class TestBlockingBehaviour:
    def test_subjective_adj_blocks_plan(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The API shall be fast and reliable."
        )
        assert result["blocks_plan_create"] is True

    def test_loophole_blocks_plan(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The system shall respond if possible."
        )
        assert result["blocks_plan_create"] is True

    def test_modal_weakness_blocks_plan(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The system should return a result."
        )
        assert result["blocks_plan_create"] is True

    def test_file_exists_ac_does_not_block(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "File exists: src/bob3/full_22_smell_linter_extension_f_r7_410.py"
        )
        assert result["blocks_plan_create"] is False


# ---------------------------------------------------------------------------
# Optional parameters forwarded correctly
# ---------------------------------------------------------------------------

class TestOptionalParameters:
    def test_peer_criteria_forwarded_for_s22(self):
        behavior_ac = "behavior: when the user submits, the form saves"
        result_no_peer = full_22_smell_linter_extension_f_r7_410(
            behavior_ac, peer_criteria=["File exists: src/foo.py"]
        )
        smell_ids_no_peer = [f.smell_id for f in result_no_peer["findings"]]
        assert "S22" in smell_ids_no_peer

    def test_pytest_peer_suppresses_s22(self):
        behavior_ac = "behavior: when the user submits, the form saves"
        result = full_22_smell_linter_extension_f_r7_410(
            behavior_ac, peer_criteria=["pytest: tests/test_form.py -v"]
        )
        smell_ids = [f.smell_id for f in result["findings"]]
        assert "S22" not in smell_ids

    def test_known_feature_ids_forwarded_for_s17(self):
        text = "The system shall implement behavior as described in F-R7-999."
        known_ids = frozenset({"F-R7-001"})
        result = full_22_smell_linter_extension_f_r7_410(text, known_feature_ids=known_ids)
        smell_ids = [f.smell_id for f in result["findings"]]
        assert "S17" in smell_ids

    def test_none_peer_criteria_no_crash(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "The system shall be fast.", peer_criteria=None
        )
        assert isinstance(result, dict)

    def test_none_known_feature_ids_no_crash(self):
        result = full_22_smell_linter_extension_f_r7_410(
            "See F-R7-999 for details.", known_feature_ids=None
        )
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Re-exported symbols remain accessible
# ---------------------------------------------------------------------------

class TestReExportedSymbols:
    def test_detect_smells_accessible(self):
        assert callable(detect_smells)

    def test_blocks_plan_create_accessible(self):
        assert callable(blocks_plan_create)

    def test_smell_catalog_has_22_entries(self):
        assert len(SMELL_CATALOG) == 22

    def test_smell_by_id_has_22_entries(self):
        assert len(SMELL_BY_ID) == 22

    def test_blocking_smells_non_empty(self):
        assert len(BLOCKING_SMELLS) > 0

    def test_spacy_smells_count_7(self):
        assert len(SPACY_SMELLS) == 7

    def test_severity_of_s01_is_e(self):
        assert severity_of("S01") == "E"

    def test_is_blocking_s01_true(self):
        assert is_blocking("S01") is True

    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_spacy_backed_detectors_7(self):
        assert len(spacy_backed_detectors()) == 7

    def test_handle_missing_spacy_model_raises(self):
        with pytest.raises(SpacyModelMissingError, match="en_core_web_sm"):
            handle_missing_spacy_model()

    def test_smell_finding_class_accessible(self):
        assert SmellFinding is not None

    def test_smell_definition_class_accessible(self):
        assert SmellDefinition is not None

    def test_spacy_model_missing_error_accessible(self):
        assert SpacyModelMissingError is not None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string_no_crash(self):
        result = full_22_smell_linter_extension_f_r7_410("")
        assert result["findings"] == []
        assert result["blocks_plan_create"] is False

    def test_whitespace_only_no_crash(self):
        result = full_22_smell_linter_extension_f_r7_410("   ")
        assert isinstance(result, dict)

    def test_multiple_smells_counted_correctly(self):
        text = "The system should be fast and simple if possible, etc."
        result = full_22_smell_linter_extension_f_r7_410(text)
        total = result["error_count"] + result["warning_count"] + result["info_count"]
        assert total == len(result["findings"])
        assert total >= 3
