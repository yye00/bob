"""Tests for bob.linter.smell_detectors — the full 22-smell linter extension
to F-R7-410.

Covers: the ``detect_smells`` entry point, severity gating (E blocks
``bob plan --create``), the 22-detector catalogue, spaCy-backed detector
enumeration, boundary inputs, and the error path (invalid input raises
ValueError).
"""

from __future__ import annotations

import pytest

from bob.linter.smell_detectors import (
    detect_smells,
    blocks_plan_create,
    detector_count,
    severity_of,
    is_blocking,
    spacy_backed_detectors,
    filter_by_severity,
    SmellFinding,
)


class TestDetectSmells:
    def test_clean_ac_has_no_findings(self):
        assert detect_smells("pytest: tests/test_foo.py") == []

    def test_subjective_adjective_is_flagged_e(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert findings, "expected at least one finding"
        ids = {f.smell_id for f in findings}
        assert "S01" in ids
        assert any(f.severity == "E" for f in findings)

    def test_returns_smellfinding_instances(self):
        findings = detect_smells("The system shall be robust.")
        assert all(isinstance(f, SmellFinding) for f in findings)

    def test_findings_carry_blocks_plan_flag(self):
        findings = detect_smells("The system shall be fast.")
        for f in findings:
            assert f.blocks_plan == (f.severity == "E")


class TestSeverityGating:
    def test_e_severity_blocks_plan_create(self):
        findings = detect_smells("The system shall be fast.")
        assert blocks_plan_create(findings) is True

    def test_clean_ac_does_not_block(self):
        assert blocks_plan_create(detect_smells("pytest: tests/test_x.py")) is False

    def test_empty_findings_do_not_block(self):
        assert blocks_plan_create([]) is False

    def test_severity_of_known_smells(self):
        assert severity_of("S01") == "E"
        assert severity_of("S15") == "I"

    def test_is_blocking_matches_severity(self):
        assert is_blocking("S01") is True
        assert is_blocking("S15") is False


class TestCatalogue:
    def test_exactly_22_detectors(self):
        assert detector_count() == 22

    def test_seven_spacy_backed_detectors(self):
        spacy_ids = spacy_backed_detectors()
        assert len(spacy_ids) == 7
        assert set(spacy_ids) == {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}


class TestFilterBySeverity:
    def test_filters_to_matching_severity(self):
        findings = detect_smells("The system shall be fast and simple.")
        errors = filter_by_severity(findings, "E")
        assert errors
        assert all(f.severity == "E" for f in errors)

    def test_invalid_severity_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_by_severity([], "X")


class TestBoundary:
    def test_empty_string_returns_empty(self):
        assert detect_smells("") == []

    def test_whitespace_only_no_crash(self):
        assert isinstance(detect_smells("   "), list)

    def test_peer_criteria_and_feature_ids_accepted(self):
        findings = detect_smells(
            "behavior: the system logs in the user",
            peer_criteria=["pytest: tests/test_login.py"],
            known_feature_ids=frozenset({"F-R7-410"}),
        )
        assert isinstance(findings, list)


class TestErrorPath:
    def test_non_str_input_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_smells(object())

    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_smells(None)

    def test_int_input_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_smells(42)
