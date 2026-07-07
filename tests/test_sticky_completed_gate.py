"""Tests for bob.sticky_completed_gate.should_accept_status_flip.

Feature 676c4261 — Sticky-completed gate: re-evaluation cannot un-complete
persisted work.

Covers the main happy-path and guard-rail behaviours of the gate.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from bob.sticky_completed_gate import (
    apply_sticky_completed_gate,
    apply_sticky_gate,
    reset_stamp_on_ac_file_rewrite,
    should_accept_status_flip,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_ac_file(workspace: pathlib.Path, rel_path: str) -> pathlib.Path:
    """Create *rel_path* inside *workspace*, creating parent dirs."""
    target = workspace / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# artifact\n")
    return target


def _acs(paths: list[str]) -> str:
    return json.dumps([f"File exists: {p}" for p in paths])


# ---------------------------------------------------------------------------
# Gate fires — demotion BLOCKED
# ---------------------------------------------------------------------------


class TestGateFires:
    """Cases where should_accept_status_flip returns False (gate blocks flip)."""

    def test_blocks_failed_when_stamped_and_acs_pass(self, tmp_path):
        _write_ac_file(tmp_path, "src/my_module.py")
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/my_module.py"]),
            workspace=tmp_path,
        )
        assert result is False

    def test_blocks_needs_human_when_stamped_and_acs_pass(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="needs_human",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is False

    def test_blocks_pending_when_stamped_and_acs_pass(self, tmp_path):
        _write_ac_file(tmp_path, "lib/util.py")
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="pending",
            acceptance_criteria=_acs(["lib/util.py"]),
            workspace=tmp_path,
        )
        assert result is False

    def test_blocks_with_multiple_ac_files_all_present(self, tmp_path):
        _write_ac_file(tmp_path, "src/a.py")
        _write_ac_file(tmp_path, "src/b.py")
        acs = json.dumps(["File exists: src/a.py", "File exists: src/b.py"])
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=acs,
            workspace=tmp_path,
        )
        assert result is False

    def test_accepts_list_input_for_acceptance_criteria(self, tmp_path):
        _write_ac_file(tmp_path, "src/feature.py")
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=["File exists: src/feature.py"],
            workspace=tmp_path,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Gate does not fire — demotion ALLOWED (flip accepted)
# ---------------------------------------------------------------------------


class TestGateDoesNotFire:
    """Cases where should_accept_status_flip returns True (flip allowed)."""

    def test_allows_when_not_stamped(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        result = should_accept_status_flip(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_non_demoting_target_ready(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="ready",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_non_demoting_target_completed(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="completed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_when_ac_file_missing(self, tmp_path):
        # File is NOT created — AC verification fails → gate allows flip.
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/missing.py"]),
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_when_any_ac_file_missing(self, tmp_path):
        _write_ac_file(tmp_path, "src/present.py")
        # src/absent.py is not created.
        acs = json.dumps(["File exists: src/present.py", "File exists: src/absent.py"])
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=acs,
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_when_no_file_existence_acs(self, tmp_path):
        acs = json.dumps(["pytest: tests/test_foo.py", "integration: bob.evaluator"])
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=acs,
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_with_none_acceptance_criteria(self, tmp_path):
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=None,
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_with_empty_acceptance_criteria_list(self, tmp_path):
        result = should_accept_status_flip(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=[],
            workspace=tmp_path,
        )
        assert result is True

    def test_allows_non_stamped_even_when_all_acs_pass(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        result = should_accept_status_flip(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Return type is strictly bool
# ---------------------------------------------------------------------------


def test_return_type_is_bool_when_fires(tmp_path):
    _write_ac_file(tmp_path, "src/a.py")
    result = should_accept_status_flip(
        parent_completed=True,
        target_status="failed",
        acceptance_criteria=_acs(["src/a.py"]),
        workspace=tmp_path,
    )
    assert type(result) is bool  # noqa: E721


def test_return_type_is_bool_when_silent(tmp_path):
    result = should_accept_status_flip(
        parent_completed=False,
        target_status="failed",
        acceptance_criteria=None,
        workspace=tmp_path,
    )
    assert type(result) is bool  # noqa: E721


# ---------------------------------------------------------------------------
# Workspace defaults to cwd (smoke test — we don't mutate cwd in tests)
# ---------------------------------------------------------------------------


def test_workspace_defaults_to_cwd_when_not_stamped():
    """When not stamped the gate returns True without touching workspace."""
    result = should_accept_status_flip(
        parent_completed=False,
        target_status="failed",
        acceptance_criteria=None,
        workspace=None,
    )
    assert result is True


# ---------------------------------------------------------------------------
# apply_sticky_gate — canonical resolved-status entry point (AC-named function)
# ---------------------------------------------------------------------------


class TestApplyStickyGate:
    """apply_sticky_gate returns the resolved status.

    When the sticky gate fires it must keep the feature at ``'ready'`` rather
    than the requested demoting status; otherwise it returns the requested
    target status unchanged.
    """

    def test_returns_ready_when_gate_blocks_demotion(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_gate(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert resolved == "ready"

    def test_returns_target_when_not_stamped(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_gate(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert resolved == "failed"

    def test_returns_target_when_ac_file_missing(self, tmp_path):
        resolved = apply_sticky_gate(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/missing.py"]),
            workspace=tmp_path,
        )
        assert resolved == "failed"

    def test_returns_target_for_non_demoting_status(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_gate(
            parent_completed=True,
            target_status="ready",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert resolved == "ready"

    def test_returns_target_when_no_file_acs(self, tmp_path):
        resolved = apply_sticky_gate(
            parent_completed=True,
            target_status="needs_human",
            acceptance_criteria=json.dumps(["pytest: tests/test_x.py"]),
            workspace=tmp_path,
        )
        assert resolved == "needs_human"

    def test_return_type_is_str(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_gate(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert type(resolved) is str  # noqa: E721


# ---------------------------------------------------------------------------
# apply_sticky_completed_gate — AC-named canonical entry point
# ---------------------------------------------------------------------------


class TestApplyStickyCompletedGate:
    """apply_sticky_completed_gate returns the resolved status string.

    It must behave identically to apply_sticky_gate: keep a stamped feature at
    'ready' when the gate fires, otherwise return the requested status.
    """

    def test_returns_ready_when_gate_blocks_demotion(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_completed_gate(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert resolved == "ready"

    def test_returns_target_when_not_stamped(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_completed_gate(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert resolved == "failed"

    def test_returns_target_when_ac_file_missing(self, tmp_path):
        resolved = apply_sticky_completed_gate(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/missing.py"]),
            workspace=tmp_path,
        )
        assert resolved == "failed"

    def test_return_type_is_str(self, tmp_path):
        _write_ac_file(tmp_path, "src/mod.py")
        resolved = apply_sticky_completed_gate(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=_acs(["src/mod.py"]),
            workspace=tmp_path,
        )
        assert type(resolved) is str  # noqa: E721

    def test_invalid_parent_completed_raises(self, tmp_path):
        with pytest.raises(ValueError, match="parent_completed"):
            apply_sticky_completed_gate(
                parent_completed="yes",  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=tmp_path,
            )


# ---------------------------------------------------------------------------
# reset_stamp_on_ac_file_rewrite — clears stamp only on a real AC-file rewrite
# ---------------------------------------------------------------------------


class TestResetStampOnAcFileRewrite:
    """The stamp resets only when a refinement rewrote an AC-named source file."""

    def test_resets_when_ac_file_in_rewritten_set(self, tmp_path):
        calls: list[str] = []
        did_reset = reset_stamp_on_ac_file_rewrite(
            feature_id="feat-123",
            acceptance_criteria=_acs(["src/mod.py", "src/other.py"]),
            rewritten_files=["src/mod.py"],
            reset_fn=lambda fid: calls.append(fid),
        )
        assert did_reset is True
        assert calls == ["feat-123"]

    def test_no_reset_when_no_ac_file_rewritten(self, tmp_path):
        calls: list[str] = []
        did_reset = reset_stamp_on_ac_file_rewrite(
            feature_id="feat-123",
            acceptance_criteria=_acs(["src/mod.py"]),
            rewritten_files=["docs/readme.md", "src/unrelated.py"],
            reset_fn=lambda fid: calls.append(fid),
        )
        assert did_reset is False
        assert calls == []

    def test_no_reset_when_rewritten_files_empty(self, tmp_path):
        calls: list[str] = []
        did_reset = reset_stamp_on_ac_file_rewrite(
            feature_id="feat-123",
            acceptance_criteria=_acs(["src/mod.py"]),
            rewritten_files=[],
            reset_fn=lambda fid: calls.append(fid),
        )
        assert did_reset is False
        assert calls == []

    def test_no_reset_when_no_file_acs(self, tmp_path):
        calls: list[str] = []
        did_reset = reset_stamp_on_ac_file_rewrite(
            feature_id="feat-123",
            acceptance_criteria=json.dumps(["pytest: tests/test_x.py"]),
            rewritten_files=["src/mod.py"],
            reset_fn=lambda fid: calls.append(fid),
        )
        assert did_reset is False
        assert calls == []

    def test_return_type_is_bool(self, tmp_path):
        did_reset = reset_stamp_on_ac_file_rewrite(
            feature_id="feat-123",
            acceptance_criteria=_acs(["src/mod.py"]),
            rewritten_files=["src/mod.py"],
            reset_fn=lambda fid: None,
        )
        assert type(did_reset) is bool  # noqa: E721

    def test_invalid_feature_id_raises(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            reset_stamp_on_ac_file_rewrite(
                feature_id="",
                acceptance_criteria=_acs(["src/mod.py"]),
                rewritten_files=["src/mod.py"],
                reset_fn=lambda fid: None,
            )

    def test_invalid_rewritten_files_raises(self, tmp_path):
        with pytest.raises(ValueError, match="rewritten_files"):
            reset_stamp_on_ac_file_rewrite(
                feature_id="feat-123",
                acceptance_criteria=_acs(["src/mod.py"]),
                rewritten_files="src/mod.py",  # type: ignore[arg-type]
                reset_fn=lambda fid: None,
            )
