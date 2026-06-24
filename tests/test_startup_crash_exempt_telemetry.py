"""Tests: startup_crash_exempt telemetry — outcome fields, evidence strings, and function
correctness for supporting diagnostic/telemetry use cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.startup_crash_exempt import (
    ExemptDecision,
    StartupCrashExemptOutcome,
    compute_artifact_count_after_spawn,
    exit_signature_matches_transport_transient,
    exponential_backoff_seconds,
    try_exempt,
)


class TestStartupCrashExemptOutcomeFields:
    """Verify that StartupCrashExemptOutcome carries all telemetry fields."""

    def test_outcome_has_decision_field(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert hasattr(outcome, "decision")

    def test_outcome_has_backoff_seconds_field(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert hasattr(outcome, "backoff_seconds")

    def test_outcome_has_artifact_count_field(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert hasattr(outcome, "artifact_count")

    def test_outcome_has_exempt_counter_after_field(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert hasattr(outcome, "exempt_counter_after")

    def test_outcome_has_evidence_field(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert hasattr(outcome, "evidence")


class TestExitSignatureMatchesTransportTransient:
    """Unit tests for exit_signature_matches_transport_transient."""

    def test_empty_string_returns_false(self) -> None:
        assert exit_signature_matches_transport_transient("") is False

    def test_none_returns_false(self) -> None:
        assert exit_signature_matches_transport_transient(None) is False

    def test_self_signed_cert_returns_true(self) -> None:
        assert exit_signature_matches_transport_transient(
            "Error: self signed certificate in certificate chain"
        ) is True

    def test_econnreset_returns_true(self) -> None:
        assert exit_signature_matches_transport_transient("ECONNRESET") is True

    def test_unrelated_error_returns_false(self) -> None:
        assert exit_signature_matches_transport_transient(
            "ImportError: No module named 'foo'"
        ) is False

    def test_assertion_error_returns_false(self) -> None:
        assert exit_signature_matches_transport_transient(
            "AssertionError: expected True got False"
        ) is False

    def test_case_insensitive_matching(self) -> None:
        assert exit_signature_matches_transport_transient(
            "SELF SIGNED CERTIFICATE IN CERTIFICATE CHAIN"
        ) is True

    def test_returns_bool_type(self) -> None:
        result = exit_signature_matches_transport_transient("ECONNRESET")
        assert isinstance(result, bool)

    def test_connection_timed_out_returns_true(self) -> None:
        assert exit_signature_matches_transport_transient("connection timed out") is True

    def test_socket_hang_up_returns_true(self) -> None:
        assert exit_signature_matches_transport_transient("socket hang up") is True


class TestComputeArtifactCountAfterSpawn:
    """Unit tests for compute_artifact_count_after_spawn."""

    def test_none_workspace_returns_zero(self) -> None:
        assert compute_artifact_count_after_spawn(None) == 0

    def test_nonexistent_workspace_returns_zero(self) -> None:
        assert compute_artifact_count_after_spawn("/nonexistent/path/xyz") == 0

    def test_empty_workspace_returns_zero(self, tmp_path: Path) -> None:
        assert compute_artifact_count_after_spawn(tmp_path) == 0

    def test_workspace_with_src_py_file_returns_count(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.py").write_text("# code\n")
        assert compute_artifact_count_after_spawn(tmp_path) == 1

    def test_workspace_with_tests_py_file_returns_count(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_module.py").write_text("def test_x(): pass\n")
        assert compute_artifact_count_after_spawn(tmp_path) == 1

    def test_never_raises_on_missing_workspace(self) -> None:
        result = compute_artifact_count_after_spawn("/does/not/exist/ever")
        assert result == 0

    def test_never_raises_on_none_workspace(self) -> None:
        result = compute_artifact_count_after_spawn(None)
        assert result == 0

    def test_returns_int(self, tmp_path: Path) -> None:
        result = compute_artifact_count_after_spawn(tmp_path)
        assert isinstance(result, int)


class TestCapReachedDecision:
    """try_exempt falls through to CAP_REACHED when exempt_counter >= 25."""

    def test_cap_reached_at_25(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=25,
        )
        assert outcome.decision == ExemptDecision.CAP_REACHED

    def test_cap_reached_above_25(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=30,
        )
        assert outcome.decision == ExemptDecision.CAP_REACHED

    def test_cap_reached_has_zero_backoff(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=25,
        )
        assert outcome.backoff_seconds == 0

    def test_cap_not_reached_at_24(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=24,
        )
        assert outcome.decision == ExemptDecision.EXEMPT
