"""Tests for bob.linter_22smell — the full 22-smell linter module.

Verifies that detect_smells is importable, returns the correct types,
that E-severity smells block plan --create, and that the public API
matches the 22-detector catalogue.
"""

from __future__ import annotations

import pytest

from bob.linter_22smell import (
    SmellFinding,
    blocks_plan_create,
    detect_smells,
    detector_count,
)


class TestPublicSymbols:
    def test_detect_smells_callable(self):
        assert callable(detect_smells)

    def test_blocks_plan_create_callable(self):
        assert callable(blocks_plan_create)

    def test_detector_count_is_22(self):
        assert detector_count() == 22

    def test_smell_finding_class_available(self):
        assert SmellFinding is not None


class TestDetectSmellsReturnType:
    def test_returns_list(self):
        result = detect_smells("The system shall be fast.")
        assert isinstance(result, list)

    def test_clean_text_returns_empty(self):
        result = detect_smells("pytest: tests/test_foo.py -v")
        assert result == []

    def test_each_finding_is_smell_finding(self):
        result = detect_smells("The system shall be fast and simple.")
        for finding in result:
            assert isinstance(finding, SmellFinding)

    def test_finding_has_severity(self):
        result = detect_smells("The system shall be fast.")
        assert len(result) > 0
        for finding in result:
            assert finding.severity in ("E", "W", "I")

    def test_finding_has_blocks_plan_property(self):
        result = detect_smells("The system shall be fast.")
        assert len(result) > 0
        for finding in result:
            assert hasattr(finding, "blocks_plan")


class TestEseverityBlocksPlanCreate:
    def test_subjective_adjective_detected(self):
        findings = detect_smells("The API shall be fast and reliable.")
        e_findings = [f for f in findings if f.severity == "E"]
        assert len(e_findings) > 0

    def test_blocks_plan_create_true_for_error_findings(self):
        findings = detect_smells("The system shall be fast if possible.")
        assert blocks_plan_create(findings) is True

    def test_blocks_plan_create_false_for_clean_text(self):
        findings = detect_smells("pytest: tests/test_foo.py -v")
        assert blocks_plan_create(findings) is False


class TestEdgeCases:
    def test_empty_string_returns_empty(self):
        result = detect_smells("")
        assert result == []

    def test_whitespace_only_returns_list(self):
        result = detect_smells("   ")
        assert isinstance(result, list)

    def test_none_peer_criteria_no_crash(self):
        result = detect_smells("The system shall be fast.", peer_criteria=None)
        assert isinstance(result, list)

    def test_none_known_feature_ids_no_crash(self):
        result = detect_smells("See F-R7-999 for details.", known_feature_ids=None)
        assert isinstance(result, list)
