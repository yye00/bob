"""Tests that E-severity smells block plan creation and that detect_all / severity_of work."""

from __future__ import annotations

import pytest

from bob.spec_quality.smell_catalog import BLOCKING_SMELLS, SMELL_BY_ID
from bob.spec_quality.smell_detectors import (
    SmellFinding,
    detect_all,
    is_blocking,
    severity_of,
)


# ---------------------------------------------------------------------------
# severity_of / is_blocking API
# ---------------------------------------------------------------------------

class TestSeverityOf:
    def test_s01_is_error(self):
        assert severity_of("S01") == "E"

    def test_s02_is_warning(self):
        assert severity_of("S02") == "W"

    def test_s15_is_informational(self):
        assert severity_of("S15") == "I"

    def test_s16_is_informational(self):
        assert severity_of("S16") == "I"

    def test_unknown_smell_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("S99")

    def test_all_22_smells_return_valid_severity(self):
        valid = {"E", "W", "I"}
        for i in range(1, 23):
            sid = f"S{i:02d}"
            assert severity_of(sid) in valid


class TestIsBlocking:
    def test_error_smell_is_blocking(self):
        # S01 is E-severity -> blocks plan
        assert is_blocking("S01") is True

    def test_warning_smell_not_blocking(self):
        # S02 is W-severity -> does not block
        assert is_blocking("S02") is False

    def test_informational_smell_not_blocking(self):
        # S15 is I -> does not block
        assert is_blocking("S15") is False

    def test_all_blocking_smells_are_error_severity(self):
        for sid in BLOCKING_SMELLS:
            assert severity_of(sid) == "E"


# ---------------------------------------------------------------------------
# SmellFinding.blocks_plan property
# ---------------------------------------------------------------------------

class TestSmellFindingBlocksPlan:
    def test_error_finding_blocks_plan(self):
        findings = detect_all("The system shall be fast and simple.")
        error_findings = [f for f in findings if f.severity == "E"]
        assert len(error_findings) > 0
        for f in error_findings:
            assert f.blocks_plan is True

    def test_warning_finding_does_not_block(self):
        findings = detect_all("The report should be generated quickly.")
        warning_findings = [f for f in findings if f.severity == "W"]
        for f in warning_findings:
            assert f.blocks_plan is False

    def test_informational_finding_does_not_block(self):
        findings = detect_all("The system will be ready in the future.")
        info_findings = [f for f in findings if f.severity == "I"]
        for f in info_findings:
            assert f.blocks_plan is False


# ---------------------------------------------------------------------------
# detect_all returns correct smell IDs for known inputs
# ---------------------------------------------------------------------------

class TestDetectAll:
    def test_returns_list_of_smell_findings(self):
        findings = detect_all("The system shall be fast.")
        assert isinstance(findings, list)
        for f in findings:
            assert isinstance(f, SmellFinding)

    def test_clean_criterion_returns_no_error_findings(self):
        # A well-formed criterion with specific measurements
        clean = "The API shall respond within 200ms for 95% of requests."
        findings = detect_all(clean)
        error_findings = [f for f in findings if f.severity == "E"]
        assert len(error_findings) == 0

    def test_subjective_adj_detected_s01(self):
        findings = detect_all("The interface shall be simple and friendly.")
        smell_ids = {f.smell_id for f in findings}
        assert "S01" in smell_ids

    def test_loophole_detected_s03(self):
        findings = detect_all("The system shall store data if possible.")
        smell_ids = {f.smell_id for f in findings}
        assert "S03" in smell_ids

    def test_open_ended_enum_detected_s04(self):
        findings = detect_all("The system shall support JSON, XML, etc.")
        smell_ids = {f.smell_id for f in findings}
        assert "S04" in smell_ids

    def test_modal_weakness_detected_s09(self):
        findings = detect_all("The system should handle errors gracefully.")
        smell_ids = {f.smell_id for f in findings}
        assert "S09" in smell_ids

    def test_magic_number_detected_s11(self):
        # Number must not be followed by period (sentence end) — use a mid-sentence number
        findings = detect_all("The response time shall be under 500 for all requests.")
        smell_ids = {f.smell_id for f in findings}
        assert "S11" in smell_ids

    def test_future_drift_detected_s16(self):
        findings = detect_all("The feature will be available in the next release.")
        smell_ids = {f.smell_id for f in findings}
        assert "S16" in smell_ids

    def test_s22_with_peer_criteria_no_pytest(self):
        """behavior AC without peer pytest: criterion → S22."""
        findings = detect_all(
            "behavior: system displays error when login fails",
            peer_criteria=["File exists: src/foo.py"],
        )
        smell_ids = {f.smell_id for f in findings}
        assert "S22" in smell_ids

    def test_s22_with_pytest_peer_no_finding(self):
        """behavior AC with peer pytest: criterion → no S22."""
        findings = detect_all(
            "behavior: system displays error when login fails",
            peer_criteria=["pytest: tests/test_login.py"],
        )
        smell_ids = {f.smell_id for f in findings}
        assert "S22" not in smell_ids

    def test_s17_with_known_ids_no_dangling(self):
        """Feature ref that exists in known set → no S17 finding."""
        findings = detect_all(
            "Extends F-R7-410 as described in the spec.",
            known_feature_ids=frozenset(["F-R7-410"]),
        )
        smell_ids = {f.smell_id for f in findings}
        assert "S17" not in smell_ids

    def test_s17_with_unknown_ref_flagged(self):
        """Feature ref that is not in known set → S17 finding."""
        findings = detect_all(
            "Implements F-R9-999.",
            known_feature_ids=frozenset(["F-R7-410"]),
        )
        smell_ids = {f.smell_id for f in findings}
        assert "S17" in smell_ids

    def test_empty_string_no_crash(self):
        findings = detect_all("")
        assert isinstance(findings, list)

    def test_finding_has_required_fields(self):
        findings = detect_all("The system should be fast.")
        assert len(findings) > 0
        f = findings[0]
        assert f.smell_id
        assert f.smell_name
        assert f.severity in {"E", "W", "I"}
        assert isinstance(f.detail, str)


# ---------------------------------------------------------------------------
# plan-blocking gate integration
# ---------------------------------------------------------------------------

class TestPlanBlockingGate:
    """Simulate the gate that blocks plan --create on E-severity findings."""

    def _would_block_plan(self, text: str) -> bool:
        findings = detect_all(text)
        return any(f.blocks_plan for f in findings)

    def test_subjective_adj_blocks_plan(self):
        assert self._would_block_plan("The system shall be simple.") is True

    def test_loophole_blocks_plan(self):
        assert self._would_block_plan("Log the event if possible.") is True

    def test_warning_does_not_block_plan(self):
        # S04 (open-ended enumeration) is W → should not block
        # Use "etc." (S04/W) without any E-severity smells in the criterion
        assert self._would_block_plan("The system shall support JSON, XML, etc.") is False

    def test_clean_criterion_does_not_block(self):
        clean = "The login endpoint shall return HTTP 200 within 300ms."
        assert self._would_block_plan(clean) is False
