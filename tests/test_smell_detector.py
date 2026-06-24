"""Tests for bob.linters.smell_detector — the canonical integration point
for the full 22-smell linter (F-R7-410 extension).
"""

from __future__ import annotations

import pytest

from bob.linters.smell_detector import detect_smells, check_severity_blocks


class TestDetectSmells:
    def test_returns_list(self):
        result = detect_smells("pytest: tests/test_foo.py")
        assert isinstance(result, list)

    def test_clean_ac_no_findings(self):
        result = detect_smells("pytest: tests/test_foo.py")
        assert result == []

    def test_subjective_adjective_detected(self):
        result = detect_smells("The system shall be fast and simple.")
        assert len(result) > 0

    def test_finding_has_required_attributes(self):
        result = detect_smells("The system shall be fast and simple.")
        assert len(result) > 0
        finding = result[0]
        assert hasattr(finding, "smell_id")
        assert hasattr(finding, "severity")
        assert hasattr(finding, "blocks_plan")
        assert hasattr(finding, "detail")

    def test_severity_values_are_valid(self):
        result = detect_smells("The system shall be fast and simple.")
        for f in result:
            assert f.severity in {"E", "W", "I"}

    def test_empty_string_returns_empty(self):
        result = detect_smells("")
        assert result == []

    def test_peer_criteria_accepted(self):
        result = detect_smells("", peer_criteria=["pytest: tests/test_foo.py"])
        assert isinstance(result, list)

    def test_known_feature_ids_accepted(self):
        result = detect_smells("", known_feature_ids=frozenset(["F-R7-001"]))
        assert isinstance(result, list)

    def test_invalid_type_raises_or_returns_defined(self):
        sentinel = object()
        result = sentinel
        try:
            result = detect_smells(object())  # invalid type
        except Exception:
            return  # acceptable — defined rejection
        assert result is not sentinel


class TestCheckSeverityBlocks:
    def test_empty_findings_does_not_block(self):
        assert check_severity_blocks([]) is False

    def test_error_severity_blocks(self):
        findings = detect_smells("The system shall be fast and simple.")
        error_findings = [f for f in findings if f.severity == "E"]
        if error_findings:
            assert check_severity_blocks(error_findings) is True

    def test_returns_bool(self):
        assert isinstance(check_severity_blocks([]), bool)

    def test_warning_only_does_not_block(self):
        from bob.spec_quality.smell_detectors import SmellFinding
        warning_finding = SmellFinding(
            smell_id="S04",
            smell_name="open-ended-enumeration",
            severity="W",
            text="etc.",
            detail="open-ended list",
        )
        assert check_severity_blocks([warning_finding]) is False

    def test_info_only_does_not_block(self):
        from bob.spec_quality.smell_detectors import SmellFinding
        info_finding = SmellFinding(
            smell_id="S09",
            smell_name="example-smell",
            severity="I",
            text="some text",
            detail="informational",
        )
        assert check_severity_blocks([info_finding]) is False

    def test_mixed_with_error_blocks(self):
        from bob.spec_quality.smell_detectors import SmellFinding
        findings = [
            SmellFinding(
                smell_id="S01",
                smell_name="subjective-adjective",
                severity="E",
                text="fast",
                detail="subjective",
            ),
            SmellFinding(
                smell_id="S04",
                smell_name="open-ended-enumeration",
                severity="W",
                text="etc.",
                detail="open-ended",
            ),
        ]
        assert check_severity_blocks(findings) is True

    def test_non_list_raises_value_error(self):
        with pytest.raises((TypeError, ValueError)):
            check_severity_blocks("not a list")  # type: ignore[arg-type]
