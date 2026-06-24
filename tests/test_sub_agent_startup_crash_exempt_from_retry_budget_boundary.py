"""Boundary tests for Sub-agent startup-crash exempt from retry budget (F-R7-613).

These tests verify that boundary/minimum/zero inputs return well-defined results
rather than raising exceptions.

AC: pytest: tests/test_sub_agent_startup_crash_exempt_from_retry_budget_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than
      raising (boundary case)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bob.run_loop import classify_subagent_startup_crash, load_exemption_sidecar


# ---------------------------------------------------------------------------
# classify_subagent_startup_crash boundary tests
# ---------------------------------------------------------------------------


class TestClassifySubagentStartupCrashBoundary:
    """Boundary cases: zero/empty/minimum inputs must not raise."""

    def test_none_exit_signature_no_artifacts(self, tmp_path: Path) -> None:
        """None exit_signature: no transport match → charge (well-defined, not raising)."""
        result = classify_subagent_startup_crash(
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] in ("exempt", "charge", "cap_reached")

    def test_empty_string_exit_signature(self, tmp_path: Path) -> None:
        """Empty string exit_signature: no transport match → charge, not raise."""
        result = classify_subagent_startup_crash(
            exit_signature="",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] == "charge"

    def test_none_workspace(self) -> None:
        """None workspace: returns well-defined result (artifact_count treated as 0)."""
        result = classify_subagent_startup_crash(
            exit_signature=None,
            workspace=None,
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert "decision" in result
        assert "artifact_count" in result
        assert result["artifact_count"] == 0

    def test_nonexistent_workspace_path(self) -> None:
        """Non-existent workspace path: returns well-defined result, not raise."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace="/nonexistent/path/abc123xyz",
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] == "exempt"

    def test_exempt_counter_zero(self, tmp_path: Path) -> None:
        """Minimum valid exempt_counter (0): returns well-defined result."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 1

    def test_exempt_counter_zero_returns_all_required_keys(self, tmp_path: Path) -> None:
        """Result always has all required keys even at minimum input."""
        result = classify_subagent_startup_crash(
            exit_signature=None,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        for key in ("decision", "backoff_seconds", "artifact_count", "exempt_counter_after", "evidence"):
            assert key in result, f"Missing required key: {key!r}"

    def test_empty_workspace_directory_no_artifacts(self, tmp_path: Path) -> None:
        """Empty workspace directory: artifact_count=0, result well-defined."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["artifact_count"] == 0
        assert result["decision"] == "exempt"

    def test_at_cap_boundary_exactly_10(self, tmp_path: Path) -> None:
        """Exactly at cap (10): returns cap_reached, not raise."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert isinstance(result, dict)
        assert result["decision"] == "cap_reached"

    def test_large_exempt_counter_above_cap(self, tmp_path: Path) -> None:
        """Very large exempt_counter: returns cap_reached well-defined result."""
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=9999,
        )
        assert isinstance(result, dict)
        assert result["decision"] == "cap_reached"

    def test_whitespace_only_exit_signature(self, tmp_path: Path) -> None:
        """Whitespace-only exit_signature: no transport match → charge, not raise."""
        result = classify_subagent_startup_crash(
            exit_signature="   \t\n  ",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert isinstance(result, dict)
        assert result["decision"] in ("charge", "exempt")

    def test_backoff_seconds_non_negative(self, tmp_path: Path) -> None:
        """backoff_seconds must always be >= 0 (never negative)."""
        for sig in [None, "", "self signed certificate in certificate chain", "some random error"]:
            for counter in [0, 5, 10]:
                result = classify_subagent_startup_crash(
                    exit_signature=sig,
                    workspace=str(tmp_path),
                    exempt_counter=counter,
                )
                assert result["backoff_seconds"] >= 0, (
                    f"backoff_seconds negative for sig={sig!r}, counter={counter}: "
                    f"{result['backoff_seconds']}"
                )


# ---------------------------------------------------------------------------
# load_exemption_sidecar boundary tests
# ---------------------------------------------------------------------------


class TestLoadExemptionSidecarBoundary:
    """Boundary cases for load_exemption_sidecar."""

    def test_missing_sidecar_file_returns_zero(self, tmp_path: Path) -> None:
        """No sidecar file → returns 0 (not raise)."""
        result = load_exemption_sidecar(
            "some-feature-id-that-does-not-exist",
            sidecar_dir=str(tmp_path),
        )
        assert result == 0

    def test_empty_sidecar_file_returns_zero(self, tmp_path: Path) -> None:
        """Empty sidecar file → returns 0."""
        feature_id = "test-feature-empty"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 0

    def test_zero_count_sidecar_returns_zero(self, tmp_path: Path) -> None:
        """Sidecar file containing '0' → returns 0."""
        feature_id = "test-feature-zero"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("0")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 0

    def test_nonexistent_sidecar_dir_returns_zero(self) -> None:
        """Non-existent sidecar directory → returns 0 (not raise)."""
        result = load_exemption_sidecar(
            "any-feature-id",
            sidecar_dir="/nonexistent/directory/xyz123",
        )
        assert result == 0

    def test_empty_feature_id_returns_zero(self, tmp_path: Path) -> None:
        """Empty string feature_id → returns 0 (boundary: no file possible)."""
        result = load_exemption_sidecar("", sidecar_dir=str(tmp_path))
        assert result == 0

    def test_whitespace_trimmed_count(self, tmp_path: Path) -> None:
        """Sidecar file with whitespace-padded number → correctly parsed."""
        feature_id = "test-feature-ws"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("  5  \n")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 5

    def test_minimum_positive_count(self, tmp_path: Path) -> None:
        """Sidecar file with '1' → returns 1."""
        feature_id = "test-feature-one"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("1")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 1

    def test_env_var_sidecar_dir_used_when_no_explicit_dir(self, tmp_path: Path, monkeypatch) -> None:
        """BOB_STARTUP_EXEMPT_DIR env var used when sidecar_dir is None."""
        feature_id = "test-feature-env"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("7")
        monkeypatch.setenv("BOB_STARTUP_EXEMPT_DIR", str(tmp_path))
        result = load_exemption_sidecar(feature_id, sidecar_dir=None)
        assert result == 7
