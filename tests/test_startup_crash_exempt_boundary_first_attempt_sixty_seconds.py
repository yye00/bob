"""Tests: boundary — first exempt attempt uses exactly 60 seconds backoff."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.startup_crash_exempt import (
    ExemptDecision,
    exponential_backoff_seconds,
    try_exempt,
)


class TestFirstAttemptSixtySeconds:
    """At exempt_counter=0, the backoff MUST be exactly 60 seconds.

    This boundary is load-bearing: it ensures the first transport-transient
    retry waits long enough for the MCP transport to recover, without
    introducing unnecessary delay when the cert error is transient.
    """

    def test_exponential_backoff_at_zero_is_sixty(self) -> None:
        assert exponential_backoff_seconds(0) == 60

    def test_try_exempt_first_attempt_backoff_sixty(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.backoff_seconds == 60

    def test_try_exempt_second_attempt_backoff_one_twenty(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=1,
        )
        assert outcome.backoff_seconds == 120

    def test_try_exempt_third_attempt_backoff_two_forty(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=2,
        )
        assert outcome.backoff_seconds == 240

    def test_first_attempt_counter_becomes_one(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.exempt_counter_after == 1

    def test_backoff_strictly_greater_than_zero_on_first_attempt(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.backoff_seconds > 0

    def test_first_attempt_not_cap_reached(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision != ExemptDecision.CAP_REACHED

    def test_first_attempt_not_charge(self, tmp_path: Path) -> None:
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision != ExemptDecision.CHARGE

    def test_last_pre_cap_attempt_backoff_still_1800(self, tmp_path: Path) -> None:
        """At exempt_counter=24 (one before cap), backoff is 1800 (capped)."""
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=24,
        )
        assert outcome.decision == ExemptDecision.EXEMPT
        assert outcome.backoff_seconds == 1800

    def test_cap_boundary_24_is_exempt_25_is_cap_reached(self, tmp_path: Path) -> None:
        outcome_24 = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=24,
        )
        outcome_25 = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=25,
        )
        assert outcome_24.decision == ExemptDecision.EXEMPT
        assert outcome_25.decision == ExemptDecision.CAP_REACHED
