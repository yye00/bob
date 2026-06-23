"""Tests: try_exempt charges a retry when artifact_count > 0, even on transport transient exit."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.startup_crash_exempt import (
    ExemptDecision,
    StartupCrashExemptOutcome,
    try_exempt,
)


def _create_src_file(workspace: Path, name: str = "feature.py") -> Path:
    """Create a Python file in workspace/src/bob3/."""
    src = workspace / "src" / "bob3"
    src.mkdir(parents=True, exist_ok=True)
    f = src / name
    f.write_text("# implementation\n")
    return f


def _create_test_file(workspace: Path, name: str = "test_feature.py") -> Path:
    """Create a Python test file in workspace/tests/."""
    tests = workspace / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    f = tests / name
    f.write_text("def test_something(): pass\n")
    return f


class TestChargesRetryOnArtifacts:
    """try_exempt MUST charge a retry when artifacts are present,
    even when the exit signature matches a transport-transient pattern."""

    def test_transport_sig_plus_src_artifact_charges_retry(self, tmp_path: Path) -> None:
        _create_src_file(tmp_path)
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE

    def test_transport_sig_plus_test_artifact_charges_retry(self, tmp_path: Path) -> None:
        _create_test_file(tmp_path)
        outcome = try_exempt(
            exit_signature="ECONNRESET: read connection reset",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE

    def test_transport_sig_plus_multiple_artifacts_charges_retry(self, tmp_path: Path) -> None:
        _create_src_file(tmp_path, "module_a.py")
        _create_src_file(tmp_path, "module_b.py")
        _create_test_file(tmp_path, "test_a.py")
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE

    def test_charge_outcome_has_zero_backoff(self, tmp_path: Path) -> None:
        _create_src_file(tmp_path)
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.backoff_seconds == 0

    def test_charge_outcome_reports_artifact_count(self, tmp_path: Path) -> None:
        _create_src_file(tmp_path, "a.py")
        _create_src_file(tmp_path, "b.py")
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.artifact_count >= 2

    def test_charge_does_not_increment_exempt_counter(self, tmp_path: Path) -> None:
        _create_src_file(tmp_path)
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=5,
        )
        assert outcome.exempt_counter_after == 5

    def test_non_transport_sig_no_artifacts_charges_retry(self, tmp_path: Path) -> None:
        """An unrecognised exit signature with no artifacts also charges retry."""
        outcome = try_exempt(
            exit_signature="implementation error: assertion failed at line 42",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE

    def test_yaml_artifact_counts_as_artifact(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.yaml").write_text("key: value\n")
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert outcome.decision == ExemptDecision.CHARGE
        assert outcome.artifact_count >= 1

    def test_charge_outcome_evidence_mentions_artifact_count(self, tmp_path: Path) -> None:
        _create_src_file(tmp_path)
        outcome = try_exempt(
            exit_signature="self signed certificate in certificate chain",
            workspace=tmp_path,
            exempt_counter=0,
        )
        assert "artifact_count" in outcome.evidence
