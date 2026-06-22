"""Tests for classify_subagent_startup_crash and check_worktree_artifacts in run_loop.

AC: pytest: tests/test_run_loop_subagent_crash_exempt.py
    integration: bob3.run_loop

Covers the F-R7-613 startup-crash exemption feature:
- classify_subagent_startup_crash returns correct decision for transport crashes
- classify_subagent_startup_crash returns charge for work-loss crashes
- classify_subagent_startup_crash enforces the 10-exemption lifetime cap
- check_worktree_artifacts counts Python files under .worktrees/hotfix-*/src/bob3/
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bob3.run_loop import (
    check_worktree_artifacts,
    classify_subagent_startup_crash,
    compute_persisted_artifact_count,
    load_exemption_sidecar,
)


# ---------------------------------------------------------------------------
# classify_subagent_startup_crash — transport crash (exempt) cases
# ---------------------------------------------------------------------------


class TestClassifyTransportCrashExempt:
    """Transport-transient crashes with no artifacts must be exempted."""

    def test_self_signed_cert_no_artifacts_exempt(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"
        assert result["artifact_count"] == 0
        assert result["exempt_counter_after"] == 1
        assert result["backoff_seconds"] >= 0

    def test_connection_reset_no_artifacts_exempt(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="ConnectionResetError: [Errno 104] Connection reset by peer",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_read_timeout_no_artifacts_exempt(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="ReadTimeout: HTTPSConnectionPool timed out",
            workspace=str(tmp_path),
            exempt_counter=2,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 3

    def test_broken_pipe_no_artifacts_exempt(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="BrokenPipeError: [Errno 32] Broken pipe",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_connection_reset_lowercase_no_artifacts_exempt(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="connection reset by peer during MCP handshake",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_exempt_result_has_all_required_keys(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        for key in ("decision", "backoff_seconds", "artifact_count", "exempt_counter_after", "evidence"):
            assert key in result, f"Missing key: {key!r}"

    def test_backoff_increases_with_counter(self, tmp_path: Path) -> None:
        result0 = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        result3 = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result3["backoff_seconds"] >= result0["backoff_seconds"]


# ---------------------------------------------------------------------------
# classify_subagent_startup_crash — work-loss crash (charge) cases
# ---------------------------------------------------------------------------


class TestClassifyWorkLossCrashCharge:
    """Crashes with persisted artifacts must charge a retry (work-loss path)."""

    def test_transport_crash_with_artifacts_charges(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "something.py").write_text("x = 1")
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["artifact_count"] > 0

    def test_unrecognized_crash_no_artifacts_charges(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="Some random unexpected error occurred",
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
        assert result["artifact_count"] == 0

    def test_charge_does_not_increment_exempt_counter(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="Some random error",
            workspace=str(tmp_path),
            exempt_counter=3,
        )
        assert result["decision"] == "charge"
        assert result["exempt_counter_after"] == 3


# ---------------------------------------------------------------------------
# classify_subagent_startup_crash — lifetime cap enforcement
# ---------------------------------------------------------------------------


class TestClassifyLifetimeCap:
    """After 10 exemptions the decision must be cap_reached."""

    def test_at_cap_returns_cap_reached(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["decision"] == "cap_reached"

    def test_above_cap_returns_cap_reached(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(tmp_path),
            exempt_counter=100,
        )
        assert result["decision"] == "cap_reached"

    def test_just_below_cap_returns_exempt(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(tmp_path),
            exempt_counter=9,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 10

    def test_cap_reached_counter_not_incremented(self, tmp_path: Path) -> None:
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(tmp_path),
            exempt_counter=10,
        )
        assert result["decision"] == "cap_reached"
        assert result["exempt_counter_after"] == 10


# ---------------------------------------------------------------------------
# check_worktree_artifacts
# ---------------------------------------------------------------------------


class TestCheckWorktreeArtifacts:
    """check_worktree_artifacts counts .py files under .worktrees/hotfix-*/src/bob3/."""

    def test_no_worktrees_dir_returns_zero(self, tmp_path: Path) -> None:
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 0

    def test_empty_worktrees_dir_returns_zero(self, tmp_path: Path) -> None:
        (tmp_path / ".worktrees").mkdir()
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 0

    def test_hotfix_worktree_with_py_files_counted(self, tmp_path: Path) -> None:
        bob3_src = tmp_path / ".worktrees" / "hotfix-abc" / "src" / "bob3"
        bob3_src.mkdir(parents=True)
        (bob3_src / "module.py").write_text("x = 1")
        (bob3_src / "helper.py").write_text("y = 2")
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 2

    def test_non_hotfix_worktree_not_counted(self, tmp_path: Path) -> None:
        worktrees = tmp_path / ".worktrees"
        worktrees.mkdir()
        other = worktrees / "feature-branch" / "src" / "bob3"
        other.mkdir(parents=True)
        (other / "module.py").write_text("x = 1")
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 0

    def test_multiple_hotfix_worktrees_all_counted(self, tmp_path: Path) -> None:
        for wt in ("hotfix-1", "hotfix-2", "hotfix-abc"):
            d = tmp_path / ".worktrees" / wt / "src" / "bob3"
            d.mkdir(parents=True)
            (d / "file.py").write_text("x = 1")
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 3

    def test_missing_src_bob3_dir_returns_zero(self, tmp_path: Path) -> None:
        wt = tmp_path / ".worktrees" / "hotfix-xyz"
        wt.mkdir(parents=True)
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 0

    def test_non_py_files_not_counted(self, tmp_path: Path) -> None:
        d = tmp_path / ".worktrees" / "hotfix-abc" / "src" / "bob3"
        d.mkdir(parents=True)
        (d / "data.json").write_text("{}")
        (d / "notes.txt").write_text("notes")
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 0

    def test_none_bob_root_does_not_raise(self) -> None:
        result = check_worktree_artifacts(bob_root=None)
        assert isinstance(result, int)
        assert result >= 0

    def test_nonexistent_bob_root_returns_zero(self) -> None:
        result = check_worktree_artifacts(bob_root="/nonexistent/path/xyz999")
        assert result == 0

    def test_nested_py_files_in_worktree_counted(self, tmp_path: Path) -> None:
        d = tmp_path / ".worktrees" / "hotfix-nest" / "src" / "bob3"
        subpkg = d / "subpkg"
        subpkg.mkdir(parents=True)
        (d / "top.py").write_text("x = 1")
        (subpkg / "sub.py").write_text("y = 2")
        result = check_worktree_artifacts(bob_root=str(tmp_path))
        assert result == 2


# ---------------------------------------------------------------------------
# compute_persisted_artifact_count
# ---------------------------------------------------------------------------


class TestComputePersistedArtifactCount:
    """Smoke tests for the artifact counter used by classify_subagent_startup_crash."""

    def test_empty_workspace_returns_zero(self, tmp_path: Path) -> None:
        assert compute_persisted_artifact_count(str(tmp_path)) == 0

    def test_py_file_in_src_counted(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.py").write_text("x = 1")
        assert compute_persisted_artifact_count(str(tmp_path)) >= 1

    def test_none_workspace_returns_zero(self) -> None:
        assert compute_persisted_artifact_count(None) == 0

    def test_nonexistent_workspace_returns_zero(self) -> None:
        assert compute_persisted_artifact_count("/nonexistent/path/abc") == 0


# ---------------------------------------------------------------------------
# Integration: load_exemption_sidecar with classify_subagent_startup_crash
# ---------------------------------------------------------------------------


class TestIntegrationSidecarWithClassify:
    """load_exemption_sidecar feeds the exempt_counter into classify_subagent_startup_crash."""

    def test_sidecar_count_used_to_classify(self, tmp_path: Path) -> None:
        feature_id = "integ-test-feature"
        sidecar_dir = tmp_path / "sidecars"
        sidecar_dir.mkdir()
        (sidecar_dir / f"{feature_id}.count").write_text("3")

        counter = load_exemption_sidecar(feature_id, sidecar_dir=str(sidecar_dir))
        assert counter == 3

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(workspace),
            exempt_counter=counter,
        )
        assert result["decision"] == "exempt"
        assert result["exempt_counter_after"] == 4

    def test_sidecar_at_cap_causes_cap_reached(self, tmp_path: Path) -> None:
        feature_id = "cap-test-feature"
        sidecar_dir = tmp_path / "sidecars"
        sidecar_dir.mkdir()
        (sidecar_dir / f"{feature_id}.count").write_text("10")

        counter = load_exemption_sidecar(feature_id, sidecar_dir=str(sidecar_dir))
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate",
            workspace=str(workspace),
            exempt_counter=counter,
        )
        assert result["decision"] == "cap_reached"
