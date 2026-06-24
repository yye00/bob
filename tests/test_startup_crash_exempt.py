"""Tests for bob.startup_crash_exempt module.

Covers try_exempt, persisted_artifact_count, compute_artifact_count_after_spawn,
exit_signature_matches_transport_transient, and exponential_backoff_seconds.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.startup_crash_exempt import (
    ExemptDecision,
    StartupCrashExemptOutcome,
    compute_artifact_count_after_spawn,
    exit_signature_matches_transport_transient,
    exponential_backoff_seconds,
    persisted_artifact_count,
    try_exempt,
)


# ---------------------------------------------------------------------------
# try_exempt: transport crash (no artifacts) → EXEMPT
# ---------------------------------------------------------------------------

class TestTryExemptTransportCrash:
    def test_self_signed_cert_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="Error: self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_econnreset_no_artifacts_returns_exempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ECONNRESET: connection reset by peer",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_exempt_increments_counter(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=2,
        )
        assert outcome.exempt_counter_after == 3

    def test_exempt_has_positive_backoff(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.backoff_seconds > 0

    def test_exempt_artifact_count_is_zero(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ECONNRESET",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.artifact_count == 0

    def test_returns_startupcrashexemptoutcome(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert isinstance(outcome, StartupCrashExemptOutcome)

    def test_none_workspace_with_transport_returns_exempt(self) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=None,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_nonexistent_workspace_with_transport_returns_exempt(self) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace="/nonexistent/path/xyz",
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.EXEMPT


# ---------------------------------------------------------------------------
# try_exempt: artifacts present → CHARGE
# ---------------------------------------------------------------------------

class TestTryExemptArtifactsPresent:
    def test_artifacts_present_returns_charge(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "feature.py").write_text("# impl")
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE

    def test_charge_does_not_increment_counter(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.py").write_text("x = 1")
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=5,
        )
        assert outcome.exempt_counter_after == 5

    def test_charge_backoff_is_zero(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "impl.py").write_text("pass")
        outcome = try_exempt(
            exit_signature="ECONNRESET",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.backoff_seconds == 0

    def test_charge_on_unclassified_no_artifacts(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="some random error without transport pattern",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE

    def test_charge_on_none_signature_no_artifacts(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature=None,
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE


# ---------------------------------------------------------------------------
# try_exempt: lifetime cap → CAP_REACHED
# ---------------------------------------------------------------------------

class TestTryExemptLifetimeCap:
    def test_cap_at_25_returns_cap_reached(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=25,
        )
        assert outcome.decision == ExemptDecision.CAP_REACHED

    def test_cap_counter_not_incremented(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="ECONNRESET",
            workspace=tmp_path,
            exempt_counter=25,
        )
        assert outcome.exempt_counter_after == 25

    def test_cap_backoff_is_zero(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate",
            workspace=tmp_path,
            exempt_counter=30,
        )
        assert outcome.backoff_seconds == 0


# ---------------------------------------------------------------------------
# persisted_artifact_count
# ---------------------------------------------------------------------------

class TestPersistedArtifactCount:
    def test_empty_workspace_returns_zero(self, tmp_path: Path) -> None:
        assert persisted_artifact_count(tmp_path) == 0

    def test_none_workspace_returns_zero(self) -> None:
        assert persisted_artifact_count(None) == 0

    def test_nonexistent_workspace_returns_zero(self) -> None:
        assert persisted_artifact_count("/path/does/not/exist/xyz123") == 0

    def test_counts_py_files_in_src(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("pass")
        (src / "b.py").write_text("pass")
        assert persisted_artifact_count(tmp_path) == 2

    def test_counts_py_files_in_tests(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_x.py").write_text("pass")
        assert persisted_artifact_count(tmp_path) == 1

    def test_matches_compute_artifact_count_after_spawn(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "impl.py").write_text("pass")
        assert persisted_artifact_count(tmp_path) == compute_artifact_count_after_spawn(tmp_path)

    def test_ignores_non_artifact_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "README.txt").write_text("doc")
        (src / "data.csv").write_text("a,b")
        assert persisted_artifact_count(tmp_path) == 0

    def test_counts_nested_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "bob"
        src.mkdir(parents=True)
        (src / "module.py").write_text("pass")
        assert persisted_artifact_count(tmp_path) >= 1


# ---------------------------------------------------------------------------
# exit_signature_matches_transport_transient
# ---------------------------------------------------------------------------

class TestExitSignatureMatchesTransportTransient:
    def test_self_signed_cert_matches(self) -> None:
        assert exit_signature_matches_transport_transient("self signed certificate in certificate chain")

    def test_econnreset_matches(self) -> None:
        assert exit_signature_matches_transport_transient("ECONNRESET error")

    def test_none_returns_false(self) -> None:
        assert not exit_signature_matches_transport_transient(None)

    def test_empty_string_returns_false(self) -> None:
        assert not exit_signature_matches_transport_transient("")

    def test_random_error_returns_false(self) -> None:
        assert not exit_signature_matches_transport_transient("AssertionError: expected 1 got 2")

    def test_etimedout_matches(self) -> None:
        assert exit_signature_matches_transport_transient("ETIMEDOUT: operation timed out")


# ---------------------------------------------------------------------------
# exponential_backoff_seconds
# ---------------------------------------------------------------------------

class TestExponentialBackoffSeconds:
    def test_counter_zero_returns_60(self) -> None:
        assert exponential_backoff_seconds(0) == 60

    def test_counter_one_returns_120(self) -> None:
        assert exponential_backoff_seconds(1) == 120

    def test_counter_two_returns_240(self) -> None:
        assert exponential_backoff_seconds(2) == 240

    def test_capped_at_1800(self) -> None:
        assert exponential_backoff_seconds(100) == 1800

    def test_negative_treated_as_zero(self) -> None:
        assert exponential_backoff_seconds(-5) == 60
