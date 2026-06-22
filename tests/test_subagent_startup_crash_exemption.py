"""Tests for handle_subagent_startup_crash_exemption (F-R7-613).

Verifies the orchestrator integration entry point:
  bob3.run_loop.handle_subagent_startup_crash_exemption

AC: pytest: tests/test_subagent_startup_crash_exemption.py
    integration: bob3.run_loop
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.run_loop import handle_subagent_startup_crash_exemption


TRANSPORT_CRASH_SIGS = [
    "self signed certificate in certificate chain",
    "ConnectionResetError: [Errno 104] Connection reset by peer",
    "ReadTimeout: HTTPSConnectionPool(host='github.com')",
    "BrokenPipeError: [Errno 32] Broken pipe",
    "MCP server 'github' Connection failed: connection refused",
    "Command failed with exit code 1\nself signed certificate in certificate chain",
]


class TestHandleSubagentStartupCrashExemption:
    """Core tests for handle_subagent_startup_crash_exemption."""

    def test_transport_crash_returns_exempt(self, tmp_path: Path) -> None:
        """Transport crash with counter=0 → decision 'exempt'."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_non_transport_crash_returns_charge(self, tmp_path: Path) -> None:
        """Normal test failure crash → decision 'charge'."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="AssertionError: assert False is True",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"

    def test_none_exit_signature_returns_charge(self, tmp_path: Path) -> None:
        """None exit_signature → decision 'charge' (no transport match)."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"

    def test_cap_reached_when_counter_at_limit(self, tmp_path: Path) -> None:
        """When exempt_counter is at cap → decision 'cap_reached'."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["decision"] == "cap_reached"

    def test_returns_all_required_keys(self, tmp_path: Path) -> None:
        """Result must contain all documented keys."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        for key in ("action", "decision", "backoff_seconds", "artifact_count",
                    "exempt_counter_after", "error_pattern", "exit_signature_excerpt", "evidence"):
            assert key in result, f"Missing required key: {key!r}"

    def test_action_equals_decision(self, tmp_path: Path) -> None:
        """'action' and 'decision' fields must agree."""
        for sig, counter in [
            ("self signed certificate in certificate chain", 0),
            ("self signed certificate in certificate chain", 10),
            ("AssertionError: assert False", 0),
        ]:
            result = handle_subagent_startup_crash_exemption(
                feature_id="feat-abc123",
                exit_signature=sig,
                workspace=str(tmp_path),
                exempt_counter=counter,
            )
            assert result["action"] == result["decision"]

    def test_exempt_counter_after_increments_on_exempt(self, tmp_path: Path) -> None:
        """When decision is 'exempt', exempt_counter_after == exempt_counter + 1."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 4

    def test_backoff_seconds_positive_on_exempt(self, tmp_path: Path) -> None:
        """On 'exempt' decision, backoff_seconds >= 0."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"
        assert result["backoff_seconds"] >= 0

    def test_backoff_seconds_zero_on_charge(self, tmp_path: Path) -> None:
        """On 'charge' decision, backoff_seconds should be 0."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="AssertionError: assert False",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["backoff_seconds"] == 0

    def test_error_pattern_set_on_exempt(self, tmp_path: Path) -> None:
        """On 'exempt' decision, error_pattern must be set (not None)."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"
        assert result["error_pattern"] is not None

    def test_error_pattern_none_on_charge(self, tmp_path: Path) -> None:
        """On 'charge' decision, error_pattern is None."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="AssertionError: assert False",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["error_pattern"] is None

    def test_exit_signature_excerpt_present(self, tmp_path: Path) -> None:
        """exit_signature_excerpt must be present and be the first 200 chars."""
        sig = "self signed certificate in certificate chain"
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature=sig,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["exit_signature_excerpt"] == sig[:200]

    def test_exit_signature_excerpt_empty_when_none_sig(self, tmp_path: Path) -> None:
        """When exit_signature is None, exit_signature_excerpt is empty string."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["exit_signature_excerpt"] == ""

    @pytest.mark.parametrize("sig", TRANSPORT_CRASH_SIGS)
    def test_all_transport_patterns_are_exempt(self, sig: str, tmp_path: Path) -> None:
        """All documented transport-transient patterns result in 'exempt'."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature=sig,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt", f"Expected 'exempt' for sig={sig!r}, got {result['decision']!r}"

    def test_nonexistent_workspace_does_not_raise(self) -> None:
        """Non-existent workspace path → returns well-defined result."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace="/nonexistent/path/xyz999",
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] == "exempt"

    def test_none_workspace_does_not_raise(self) -> None:
        """None workspace → returns well-defined result."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature=None,
            workspace=None,
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert "decision" in result

    def test_evidence_field_is_string(self, tmp_path: Path) -> None:
        """'evidence' field must always be a non-empty string."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result["evidence"], str)
        assert len(result["evidence"]) > 0

    def test_artifact_count_is_int(self, tmp_path: Path) -> None:
        """'artifact_count' must always be a non-negative int."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-abc123",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result["artifact_count"], int)
        assert result["artifact_count"] >= 0


class TestIntegrationWithRunLoop:
    """Integration: verifies handle_subagent_startup_crash_exemption is accessible from bob3.run_loop."""

    def test_importable_from_bob3_run_loop(self) -> None:
        """handle_subagent_startup_crash_exemption is importable from bob3.run_loop."""
        from bob3.run_loop import handle_subagent_startup_crash_exemption as fn
        assert callable(fn)

    def test_function_is_callable_with_keyword_args(self, tmp_path: Path) -> None:
        """Function accepts keyword-only arguments as per its signature."""
        result = handle_subagent_startup_crash_exemption(
            feature_id="feat-integration-test",
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result, dict)

    def test_decision_values_are_valid_strings(self, tmp_path: Path) -> None:
        """Decision values are always one of the three documented strings."""
        valid_decisions = {"exempt", "charge", "cap_reached"}
        for sig, counter in [
            ("self signed certificate in certificate chain", 0),
            ("self signed certificate in certificate chain", 10),
            ("random failure message", 0),
            (None, 0),
        ]:
            result = handle_subagent_startup_crash_exemption(
                feature_id="feat-abc123",
                exit_signature=sig,
                workspace=str(tmp_path),
                exempt_counter=counter,
            )
            assert result["decision"] in valid_decisions, (
                f"Unexpected decision={result['decision']!r} for sig={sig!r}, counter={counter}"
            )
