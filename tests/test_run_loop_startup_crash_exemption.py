"""Tests for check_subagent_startup_crash_exemption in bob.run_loop (F-R7-613).

Verifies that the function correctly:
- Returns 'exempt' for transport-transient crashes with no artifacts
- Returns 'charge' for work-loss crashes (artifacts present)
- Returns 'cap_reached' when lifetime cap is reached
- Emits correct telemetry events
- Integrates with classify_subagent_startup_crash
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from bob.run_loop import check_subagent_startup_crash_exemption


TRANSPORT_SIG = "self signed certificate in certificate chain"
RESET_SIG = "ConnectionResetError: [Errno 104] Connection reset by peer"
MCP_SIG = "Command failed with exit code 1\nMCP server Connection failed"
NON_TRANSPORT_SIG = "ImportError: No module named 'missing_module'"


class TestCheckSubagentStartupCrashExemptionTransportCrash:
    """Transport-transient crash → exempt decision."""

    def test_cert_error_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-001",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"
        assert result["decision"] == "exempt"

    def test_connection_reset_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-002",
            exit_signature=RESET_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"

    def test_mcp_failure_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-003",
            exit_signature=MCP_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"

    def test_nonexistent_workspace_treated_as_no_artifacts(self) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-004",
            exit_signature=TRANSPORT_SIG,
            workspace="/nonexistent/path/xyz999",
            exempt_counter=0,
        )
        assert result["action"] == "exempt"

    def test_none_workspace_treated_as_no_artifacts(self) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-005",
            exit_signature=TRANSPORT_SIG,
            workspace=None,
            exempt_counter=0,
        )
        assert result["action"] == "exempt"

    def test_exempt_increments_counter(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-006",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result["action"] == "exempt"
        assert result["exempt_counter_after"] == 4

    def test_exempt_returns_positive_backoff(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-007",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"
        assert result["backoff_seconds"] > 0

    def test_exempt_sets_error_pattern(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-008",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "exempt"
        assert result["error_pattern"] is not None
        assert "transport" in result["error_pattern"].lower()

    def test_exempt_includes_exit_signature_excerpt(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-009",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["exit_signature_excerpt"] == TRANSPORT_SIG[:200]


class TestCheckSubagentStartupCrashExemptionCharge:
    """Work-loss crash or unclassified → charge decision."""

    def test_non_transport_signature_returns_charge(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-010",
            exit_signature=NON_TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"
        assert result["decision"] == "charge"

    def test_none_signature_returns_charge(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-011",
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"

    def test_empty_signature_returns_charge(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-012",
            exit_signature="",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"

    def test_artifacts_present_returns_charge_even_with_transport_sig(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "impl.py").write_text("x = 1")
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-013",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"
        assert result["artifact_count"] > 0

    def test_charge_backoff_is_zero(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-014",
            exit_signature=NON_TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"
        assert result["backoff_seconds"] == 0

    def test_charge_error_pattern_is_none(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-015",
            exit_signature=NON_TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["action"] == "charge"
        assert result["error_pattern"] is None


class TestCheckSubagentStartupCrashExemptionCapReached:
    """Lifetime cap reached → cap_reached decision."""

    def test_cap_reached_at_10(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-016",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["action"] == "cap_reached"
        assert result["decision"] == "cap_reached"

    def test_cap_reached_above_10(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-017",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=50,
        )
        assert result["action"] == "cap_reached"

    def test_cap_reached_backoff_is_zero(self, tmp_path: Path) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-018",
            exit_signature=TRANSPORT_SIG,
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["action"] == "cap_reached"
        assert result["backoff_seconds"] == 0


class TestCheckSubagentStartupCrashExemptionReturnShape:
    """Result dict always has all required keys."""

    @pytest.mark.parametrize("sig,counter,expected_action", [
        (TRANSPORT_SIG, 0, "exempt"),
        (NON_TRANSPORT_SIG, 0, "charge"),
        (None, 0, "charge"),
        (TRANSPORT_SIG, 10, "cap_reached"),
    ])
    def test_all_required_keys_present(
        self,
        tmp_path: Path,
        sig: str | None,
        counter: int,
        expected_action: str,
    ) -> None:
        result = check_subagent_startup_crash_exemption(
            feature_id="feat-shape",
            exit_signature=sig,
            workspace=str(tmp_path),
            exempt_counter=counter,
        )
        for key in ("action", "decision", "backoff_seconds", "artifact_count",
                    "exempt_counter_after", "error_pattern", "exit_signature_excerpt",
                    "evidence"):
            assert key in result, f"Missing key {key!r} for sig={sig!r}, counter={counter}"
        assert result["action"] == expected_action

    def test_action_and_decision_always_equal(self, tmp_path: Path) -> None:
        for sig, counter in [(TRANSPORT_SIG, 0), (NON_TRANSPORT_SIG, 0), (TRANSPORT_SIG, 10)]:
            result = check_subagent_startup_crash_exemption(
                feature_id="feat-alias",
                exit_signature=sig,
                workspace=str(tmp_path),
                exempt_counter=counter,
            )
            assert result["action"] == result["decision"]


class TestCheckSubagentStartupCrashExemptionTelemetry:
    """Telemetry events are emitted correctly."""

    def test_exempt_emits_telemetry_event(self, tmp_path: Path, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="bob.run_loop"):
            check_subagent_startup_crash_exemption(
                feature_id="feat-telemetry-exempt",
                exit_signature=TRANSPORT_SIG,
                workspace=str(tmp_path),
                exempt_counter=0,
            )
        events = [r.message for r in caplog.records]
        found = any("SUBAGENT_STARTUP_CRASH_EXEMPT" in e for e in events)
        assert found, f"Expected SUBAGENT_STARTUP_CRASH_EXEMPT in logs, got: {events}"

    def test_cap_reached_emits_telemetry_event(self, tmp_path: Path, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="bob.run_loop"):
            check_subagent_startup_crash_exemption(
                feature_id="feat-telemetry-cap",
                exit_signature=TRANSPORT_SIG,
                workspace=str(tmp_path),
                exempt_counter=10,
            )
        events = [r.message for r in caplog.records]
        found = any("SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED" in e for e in events)
        assert found, f"Expected SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED in logs, got: {events}"

    def test_exempt_telemetry_includes_feature_id(self, tmp_path: Path, caplog) -> None:
        fid = "feat-telemetry-fid-check"
        with caplog.at_level(logging.INFO, logger="bob.run_loop"):
            check_subagent_startup_crash_exemption(
                feature_id=fid,
                exit_signature=TRANSPORT_SIG,
                workspace=str(tmp_path),
                exempt_counter=0,
            )
        events = [r.message for r in caplog.records]
        found = any(fid in e for e in events)
        assert found, f"Expected feature_id {fid!r} in log events"
