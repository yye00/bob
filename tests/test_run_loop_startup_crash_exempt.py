"""Tests for run_loop startup-crash exemption functions.

Covers classify_subagent_startup_crash and check_transport_transient_signature
as required by AC: pytest: tests/test_run_loop_startup_crash_exempt.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.run_loop import (
    classify_subagent_startup_crash,
    check_transport_transient_signature,
)


# ---------------------------------------------------------------------------
# classify_subagent_startup_crash
# ---------------------------------------------------------------------------


class TestClassifySubagentStartupCrash:
    """Core decision logic: exempt vs charge vs cap_reached."""

    def test_transport_crash_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        """Transport error + no artifacts → exempt (free retry)."""
        result = classify_subagent_startup_crash(
            exit_signature="Command failed with exit code 1\nMCP server connection failed",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_self_signed_cert_returns_exempt(self, tmp_path: Path) -> None:
        """self signed certificate pattern matches transport transient."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_connection_reset_returns_exempt(self, tmp_path: Path) -> None:
        """ConnectionResetError matches transport transient."""
        result = classify_subagent_startup_crash(
            exit_signature="ConnectionResetError: [Errno 104] Connection reset by peer",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_broken_pipe_returns_exempt(self, tmp_path: Path) -> None:
        """broken pipe matches transport transient."""
        result = classify_subagent_startup_crash(
            exit_signature="BrokenPipeError: broken pipe",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_read_timeout_returns_exempt(self, tmp_path: Path) -> None:
        """ReadTimeout matches transport transient."""
        result = classify_subagent_startup_crash(
            exit_signature="ReadTimeout: HTTPSConnectionPool host='api.github.com'",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_exempt_increments_counter(self, tmp_path: Path) -> None:
        """Successful exemption increments exempt_counter_after by 1."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 4

    def test_exempt_provides_positive_backoff(self, tmp_path: Path) -> None:
        """Exempted crash includes a non-negative backoff_seconds."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["backoff_seconds"] >= 0

    def test_artifacts_in_src_subdir_returns_charge(self, tmp_path: Path) -> None:
        """Artifacts in workspace src/ subdir → charge (work-loss crash)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "some_module.py").write_text("x = 1")
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["artifact_count"] > 0

    def test_no_transport_sig_no_artifacts_returns_charge(self, tmp_path: Path) -> None:
        """No transport pattern + no artifacts → unclassified → charge."""
        result = classify_subagent_startup_crash(
            exit_signature="Segmentation fault (core dumped)",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"

    def test_at_cap_returns_cap_reached(self, tmp_path: Path) -> None:
        """exempt_counter >= 10 → cap_reached regardless of signature."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["decision"] == "cap_reached"

    def test_above_cap_returns_cap_reached(self, tmp_path: Path) -> None:
        """exempt_counter > 10 → cap_reached."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=50,
        )
        assert result["decision"] == "cap_reached"

    def test_cap_reached_does_not_increment_counter(self, tmp_path: Path) -> None:
        """At cap, exempt_counter_after == exempt_counter (no increment)."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["exempt_counter_after"] == 10

    def test_result_contains_all_required_keys(self, tmp_path: Path) -> None:
        """Result always has all five required keys."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        for key in ("decision", "backoff_seconds", "artifact_count", "exempt_counter_after", "evidence"):
            assert key in result, f"Missing key: {key!r}"

    def test_charge_result_zero_backoff(self, tmp_path: Path) -> None:
        """charge decision has backoff_seconds == 0."""
        result = classify_subagent_startup_crash(
            exit_signature="some unknown error",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["backoff_seconds"] == 0

    def test_decision_is_one_of_three_valid_values(self, tmp_path: Path) -> None:
        """Decision is always one of the three documented values."""
        for sig, counter in [
            ("self signed certificate", 0),
            ("some random error", 0),
            ("self signed certificate", 10),
        ]:
            result = classify_subagent_startup_crash(
                exit_signature=sig, workspace=str(tmp_path), exempt_counter=counter
            )
            assert result["decision"] in ("exempt", "charge", "cap_reached"), (
                f"Unexpected decision {result['decision']!r} for sig={sig!r}, counter={counter}"
            )

    def test_evidence_is_non_empty_string(self, tmp_path: Path) -> None:
        """evidence field is always a non-empty string."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result["evidence"], str)
        assert len(result["evidence"]) > 0

    def test_connection_failed_mcp_server_pattern(self, tmp_path: Path) -> None:
        """'Connection failed' + 'MCP server' pattern triggers exemption."""
        result = classify_subagent_startup_crash(
            exit_signature=(
                "Command failed with exit code 1\n"
                "MCP server: Connection failed: evaluator"
            ),
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_backoff_grows_with_counter(self, tmp_path: Path) -> None:
        """backoff_seconds at counter=3 should be >= backoff at counter=0."""
        r0 = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        r3 = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert r3["backoff_seconds"] >= r0["backoff_seconds"]


# ---------------------------------------------------------------------------
# check_transport_transient_signature
# ---------------------------------------------------------------------------


class TestCheckTransportTransientSignature:
    """Verify check_transport_transient_signature returns correct structure."""

    def test_transport_pattern_detected(self) -> None:
        """Known transport pattern → is_transport_transient=True."""
        result = check_transport_transient_signature(
            "self signed certificate in certificate chain"
        )
        assert result["is_transport_transient"] is True

    def test_non_transport_pattern_not_detected(self) -> None:
        """Unknown error → is_transport_transient=False."""
        result = check_transport_transient_signature("Segmentation fault")
        assert result["is_transport_transient"] is False

    def test_none_exit_signature_returns_false(self) -> None:
        """None exit_signature → is_transport_transient=False."""
        result = check_transport_transient_signature(None)
        assert result["is_transport_transient"] is False

    def test_empty_exit_signature_returns_false(self) -> None:
        """Empty string → is_transport_transient=False."""
        result = check_transport_transient_signature("")
        assert result["is_transport_transient"] is False

    def test_result_contains_all_required_keys(self) -> None:
        """Result always has all four documented keys."""
        result = check_transport_transient_signature("self signed certificate")
        for key in ("is_transport_transient", "matched_pattern", "event", "exit_signature_excerpt"):
            assert key in result, f"Missing key: {key!r}"

    def test_matched_event_string_on_transport(self) -> None:
        """Transport match emits SUBAGENT_STARTUP_CRASH_TRANSPORT_TRANSIENT event."""
        result = check_transport_transient_signature("self signed certificate")
        assert result["event"] == "SUBAGENT_STARTUP_CRASH_TRANSPORT_TRANSIENT"

    def test_no_event_string_on_non_transport(self) -> None:
        """Non-transport error → event is empty string."""
        result = check_transport_transient_signature("generic failure")
        assert result["event"] == ""

    def test_matched_pattern_non_none_on_transport(self) -> None:
        """Transport match → matched_pattern is not None."""
        result = check_transport_transient_signature("self signed certificate")
        assert result["matched_pattern"] is not None

    def test_matched_pattern_none_on_non_transport(self) -> None:
        """Non-transport → matched_pattern is None."""
        result = check_transport_transient_signature("some other error")
        assert result["matched_pattern"] is None

    def test_excerpt_truncated_at_200_chars(self) -> None:
        """exit_signature_excerpt is at most 200 characters."""
        long_sig = "x" * 500
        result = check_transport_transient_signature(long_sig)
        assert len(result["exit_signature_excerpt"]) <= 200

    def test_excerpt_preserves_short_signature(self) -> None:
        """Short signature is preserved fully in excerpt."""
        sig = "self signed certificate error"
        result = check_transport_transient_signature(sig)
        assert result["exit_signature_excerpt"] == sig

    def test_connection_reset_detected(self) -> None:
        """connection reset pattern → transport transient."""
        result = check_transport_transient_signature("connection reset by peer")
        assert result["is_transport_transient"] is True

    def test_mcp_server_connection_failed(self) -> None:
        """MCP server Connection failed → transport transient."""
        result = check_transport_transient_signature(
            "Command failed with exit code 1\nMCP server: Connection failed"
        )
        assert result["is_transport_transient"] is True

    def test_broken_pipe_detected(self) -> None:
        """broken pipe → transport transient."""
        result = check_transport_transient_signature("BrokenPipe: broken pipe")
        assert result["is_transport_transient"] is True

    def test_read_timeout_detected(self) -> None:
        """ReadTimeout → transport transient."""
        result = check_transport_transient_signature("ReadTimeout: timed out waiting")
        assert result["is_transport_transient"] is True

    def test_is_transport_transient_is_bool(self) -> None:
        """is_transport_transient is always a bool, never truthy int."""
        for sig in [None, "", "self signed certificate", "random error"]:
            result = check_transport_transient_signature(sig)
            assert isinstance(result["is_transport_transient"], bool)
