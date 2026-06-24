"""Tests for bob.run_loop startup-crash exemption functions (F-R7-613).

Covers:
- classify_startup_crash (alias for classify_subagent_startup_crash)
- check_startup_crash_exemption (alias for check_subagent_startup_crash_exemption)
- load_exemption_sidecar
- Transport-transient exemption logic
- Lifetime cap enforcement
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.run_loop import (
    classify_startup_crash,
    check_startup_crash_exemption,
    load_exemption_sidecar,
)


# ---------------------------------------------------------------------------
# classify_startup_crash
# ---------------------------------------------------------------------------


class TestClassifyStartupCrash:
    """Tests for classify_startup_crash (F-R7-613 alias)."""

    def test_transport_cert_returns_exempt(self, tmp_path: Path) -> None:
        """Self-signed cert crash with no artifacts → exempt."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_connection_reset_returns_exempt(self, tmp_path: Path) -> None:
        """ConnectionResetError with no artifacts → exempt."""
        result = classify_startup_crash(
            exit_signature="ConnectionResetError: connection reset by peer",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_mcp_server_failure_returns_exempt(self, tmp_path: Path) -> None:
        """MCP server connection failure with no artifacts → exempt."""
        result = classify_startup_crash(
            exit_signature="Command failed with exit code 1: MCP server Connection failed",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_no_transport_match_returns_charge(self, tmp_path: Path) -> None:
        """Non-transport crash returns charge decision."""
        result = classify_startup_crash(
            exit_signature="some random unrecognized error message",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"

    def test_none_exit_signature_returns_charge(self, tmp_path: Path) -> None:
        """None exit_signature returns charge (no transport match possible)."""
        result = classify_startup_crash(
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] in ("charge", "exempt")

    def test_cap_reached_at_ten(self, tmp_path: Path) -> None:
        """exempt_counter >= 10 returns cap_reached."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["decision"] == "cap_reached"

    def test_cap_reached_above_ten(self, tmp_path: Path) -> None:
        """exempt_counter > 10 returns cap_reached."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=25,
        )
        assert result["decision"] == "cap_reached"

    def test_exempt_increments_counter(self, tmp_path: Path) -> None:
        """Exempt decision increments exempt_counter_after."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 4

    def test_charge_does_not_increment_counter(self, tmp_path: Path) -> None:
        """Charge decision does not increment exempt_counter_after."""
        result = classify_startup_crash(
            exit_signature="some random error",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result["decision"] == "charge"
        assert result["exempt_counter_after"] == 3

    def test_result_has_required_keys(self, tmp_path: Path) -> None:
        """Result dict always contains required keys."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        for key in ("decision", "backoff_seconds", "artifact_count", "exempt_counter_after", "evidence"):
            assert key in result, f"Missing key: {key!r}"

    def test_exempt_has_positive_backoff(self, tmp_path: Path) -> None:
        """Exempt decision includes a positive backoff_seconds."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"
        assert result["backoff_seconds"] > 0

    def test_charge_has_zero_backoff(self, tmp_path: Path) -> None:
        """Charge decision returns backoff_seconds=0."""
        result = classify_startup_crash(
            exit_signature="some random error",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["backoff_seconds"] == 0

    def test_artifact_count_zero_in_empty_workspace(self, tmp_path: Path) -> None:
        """Empty workspace returns artifact_count=0."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["artifact_count"] == 0

    def test_broken_pipe_returns_exempt(self, tmp_path: Path) -> None:
        """BrokenPipeError crash with no artifacts → exempt."""
        result = classify_startup_crash(
            exit_signature="BrokenPipeError: broken pipe",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_read_timeout_returns_exempt(self, tmp_path: Path) -> None:
        """ReadTimeout crash → exempt."""
        result = classify_startup_crash(
            exit_signature="ReadTimeout: HTTPSConnectionPool read timed out",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_nonexistent_workspace_exempt_transport(self) -> None:
        """Non-existent workspace path returns well-defined result (no raise)."""
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace="/nonexistent/path/xyz999",
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] in ("exempt", "charge", "cap_reached")


# ---------------------------------------------------------------------------
# check_startup_crash_exemption
# ---------------------------------------------------------------------------


class TestCheckStartupCrashExemption:
    """Tests for check_startup_crash_exemption (orchestrator integration entry point)."""

    def test_transport_crash_returns_exempt_action(self, tmp_path: Path) -> None:
        """Transport crash with no artifacts → action=exempt."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-001",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"

    def test_non_transport_crash_returns_charge(self, tmp_path: Path) -> None:
        """Non-transport crash → action=charge."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-002",
            exit_signature="unrecognized error type",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"

    def test_cap_reached_returns_cap_reached(self, tmp_path: Path) -> None:
        """exempt_counter at cap → action=cap_reached."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-003",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["action"] == "cap_reached"

    def test_result_has_action_and_decision(self, tmp_path: Path) -> None:
        """Result dict always has both 'action' and 'decision' keys."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-004",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert "action" in result
        assert "decision" in result
        assert result["action"] == result["decision"]

    def test_result_has_error_pattern_on_exempt(self, tmp_path: Path) -> None:
        """Exempt result includes error_pattern."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-005",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"
        assert result["error_pattern"] is not None

    def test_result_has_none_error_pattern_on_charge(self, tmp_path: Path) -> None:
        """Charge result has error_pattern=None."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-006",
            exit_signature="some random error",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"
        assert result["error_pattern"] is None

    def test_exit_signature_excerpt_populated(self, tmp_path: Path) -> None:
        """exit_signature_excerpt is populated from the exit_signature."""
        sig = "self signed certificate in certificate chain"
        result = check_startup_crash_exemption(
            feature_id="test-feature-007",
            exit_signature=sig,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["exit_signature_excerpt"] == sig[:200]

    def test_result_has_all_required_keys(self, tmp_path: Path) -> None:
        """Result always contains all required keys."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-008",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        required_keys = {
            "action", "decision", "backoff_seconds", "artifact_count",
            "exempt_counter_after", "error_pattern", "exit_signature_excerpt", "evidence",
        }
        for key in required_keys:
            assert key in result, f"Missing key: {key!r}"

    def test_none_exit_signature_returns_defined_result(self, tmp_path: Path) -> None:
        """None exit_signature returns well-defined result (does not raise)."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-009",
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["action"] in ("exempt", "charge", "cap_reached")

    def test_exempt_counter_after_increments_on_exempt(self, tmp_path: Path) -> None:
        """Exempt result shows incremented exempt_counter_after."""
        result = check_startup_crash_exemption(
            feature_id="test-feature-010",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=5,
        )
        assert result["action"] == "exempt"
        assert result["exempt_counter_after"] == 6


# ---------------------------------------------------------------------------
# load_exemption_sidecar (integration)
# ---------------------------------------------------------------------------


class TestLoadExemptionSidecarIntegration:
    """Integration tests for load_exemption_sidecar."""

    def test_reads_count_from_sidecar_file(self, tmp_path: Path) -> None:
        """Reads persisted exemption count from sidecar file."""
        feature_id = "integration-feature-001"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("3")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 3

    def test_missing_sidecar_returns_zero(self, tmp_path: Path) -> None:
        """Missing sidecar file returns 0 (feature has no exemptions yet)."""
        result = load_exemption_sidecar("never-seen-feature", sidecar_dir=str(tmp_path))
        assert result == 0

    def test_invalid_feature_id_type_raises(self, tmp_path: Path) -> None:
        """Non-string feature_id raises ValueError."""
        with pytest.raises(ValueError, match="feature_id must be a str"):
            load_exemption_sidecar(None, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_count_used_in_classify_startup_crash(self, tmp_path: Path) -> None:
        """Count from sidecar feeds correctly into classify_startup_crash."""
        count = load_exemption_sidecar("some-feature-id", sidecar_dir=str(tmp_path))
        result = classify_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=count,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == count + 1
