"""Tests: try_exempt returns EXEMPT when artifact_count == 0 and exit signature matches transport transient."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.startup_crash_exempt import (
    ExemptDecision,
    StartupCrashExemptOutcome,
    try_exempt,
)


class TestTransportCrashExemption:
    """try_exempt grants a free retry when no artifacts are present and
    the exit signature matches a transport-transient pattern."""

    def test_self_signed_cert_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="Error: self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_connection_reset_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ECONNRESET: read connection reset by peer",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_econnrefused_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ECONNREFUSED: connection refused to evaluator",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_certificate_verify_failed_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="certificate verify failed: unable to get local issuer certificate",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_mcp_connection_fail_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="MCP server plugin:github:github Connection failed: self-signed certificate",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_exempt_outcome_has_positive_backoff(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.backoff_seconds > 0

    def test_exempt_outcome_increments_counter(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=3,
        )
        assert outcome.exempt_counter_after == 4

    def test_exempt_outcome_artifact_count_zero(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ECONNRESET: connection reset",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.artifact_count == 0

    def test_exempt_outcome_has_evidence_string(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert isinstance(outcome.evidence, str)
        assert len(outcome.evidence) > 0

    def test_exempt_returns_startupcrashexemptoutcome_instance(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert isinstance(outcome, StartupCrashExemptOutcome)

    def test_missing_workspace_with_transport_signature_returns_exempt(self) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace="/nonexistent/path/does/not/exist",
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_none_workspace_with_transport_signature_returns_exempt(self) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=None,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_etimedout_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ETIMEDOUT: operation timed out",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_socket_hang_up_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="socket hang up",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT
