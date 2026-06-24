"""Boundary tests for bob.startup_crash_exempt — empty, zero, or minimum inputs.

Each test verifies that the function returns a well-defined result rather
than raising when given the smallest or emptiest possible valid input.
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


class TestTryExemptBoundary:
    """try_exempt returns well-defined outcomes for minimum/empty inputs."""

    def test_none_signature_none_workspace_zero_counter(self) -> None:
        outcome = try_exempt(exit_signature=None, workspace=None, exempt_counter=0)
        assert isinstance(outcome, StartupCrashExemptOutcome)

    def test_empty_string_signature_none_workspace(self) -> None:
        outcome = try_exempt(exit_signature="", workspace=None, exempt_counter=0)
        assert isinstance(outcome, StartupCrashExemptOutcome)

    def test_zero_counter_returns_outcome(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature=None,
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert isinstance(outcome, StartupCrashExemptOutcome)

    def test_none_workspace_zero_counter_gives_charge(self) -> None:
        outcome = try_exempt(exit_signature=None, workspace=None, exempt_counter=0)
        assert outcome.decision == ExemptDecision.CHARGE

    def test_none_signature_does_not_raise(self) -> None:
        result = try_exempt(exit_signature=None, workspace=None, exempt_counter=0)
        assert result is not None

    def test_empty_workspace_dir_does_not_raise(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature=None,
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.artifact_count == 0

    def test_counter_exactly_zero_backoff_is_defined(self, tmp_path: Path) -> None:
        backoff = exponential_backoff_seconds(0)
        assert backoff == 60

    def test_counter_exactly_cap_minus_one_returns_outcome(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=24,
        )
        assert isinstance(outcome, StartupCrashExemptOutcome)
        assert outcome.decision == ExemptDecision.EXEMPT

    def test_counter_exactly_cap_returns_cap_reached(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature=None,
            workspace=tmp_path,
            exempt_counter=25,
        )
        assert outcome.decision == ExemptDecision.CAP_REACHED

    def test_empty_string_signature_does_not_raise(self) -> None:
        result = exit_signature_matches_transport_transient("")
        assert result is False

    def test_none_signature_match_returns_false(self) -> None:
        result = exit_signature_matches_transport_transient(None)
        assert result is False

    def test_none_workspace_persisted_artifact_count_is_zero(self) -> None:
        assert persisted_artifact_count(None) == 0

    def test_empty_workspace_persisted_artifact_count_is_zero(self, tmp_path: Path) -> None:
        assert persisted_artifact_count(tmp_path) == 0

    def test_nonexistent_workspace_compute_artifact_count_zero(self) -> None:
        assert compute_artifact_count_after_spawn("/no/such/path/abc123") == 0

    def test_none_workspace_compute_artifact_count_zero(self) -> None:
        assert compute_artifact_count_after_spawn(None) == 0

    def test_minimum_backoff_at_counter_zero(self) -> None:
        assert exponential_backoff_seconds(0) >= 1

    def test_outcome_evidence_is_string_on_boundary(self) -> None:
        outcome = try_exempt(exit_signature=None, workspace=None, exempt_counter=0)
        assert isinstance(outcome.evidence, str)
        assert len(outcome.evidence) > 0
