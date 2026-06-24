"""Tests for BF-6 — Characterization AC kind (approval-test diffs for legacy code).

Covers:
  - Module and function existence
  - sample_inputs symbol availability
  - Boundary case: empty/None input returns well-defined result (no crash)
  - Invalid input raises ValueError
  - Observer phase captures snapshots
  - Verifier phase passes when behavior is unchanged
  - Verifier phase fails when behavior changes
  - parse_characterization_ac and kinds.py integration
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

import bob.bf_6_characterization_ac_kind_approval_test_diffs_legacy as bf6_mod
from bob.bf_6_characterization_ac_kind_approval_test_diffs_legacy import (
    bf_6_characterization_ac_kind_approval_test_diffs_legacy,
    sample_inputs,
)
from bob.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


# ---------------------------------------------------------------------------
# Module-level symbol checks
# ---------------------------------------------------------------------------


def test_bf_6_characterization_ac_kind_approval_test_diffs_legacy() -> None:
    """Canonical test: module exports the required function and sample_inputs."""
    assert callable(bf_6_characterization_ac_kind_approval_test_diffs_legacy)
    assert callable(sample_inputs)


def test_sample_inputs_returns_list() -> None:
    """sample_inputs returns a non-empty list of tuples."""
    inputs = sample_inputs()
    assert isinstance(inputs, list)
    assert len(inputs) > 0
    for item in inputs:
        assert isinstance(item, tuple)


def test_sample_inputs_contains_zero_boundary() -> None:
    """sample_inputs includes the (0,) boundary case."""
    inputs = sample_inputs()
    assert (0,) in inputs


# ---------------------------------------------------------------------------
# Boundary: empty / None / zero input — must NOT crash
# ---------------------------------------------------------------------------


def test_empty_none_ac_spec_returns_well_defined_result() -> None:
    """None ac_spec → passed=False with a descriptive detail (no crash)."""
    result = bf_6_characterization_ac_kind_approval_test_diffs_legacy(None)
    assert isinstance(result, dict)
    assert result["passed"] is False
    assert "detail" in result
    assert isinstance(result["detail"], str)
    assert len(result["detail"]) > 0


def test_empty_dict_ac_spec_returns_well_defined_result() -> None:
    """Empty dict ac_spec → passed=False with a descriptive detail (no crash)."""
    result = bf_6_characterization_ac_kind_approval_test_diffs_legacy({})
    assert isinstance(result, dict)
    assert result["passed"] is False


def test_empty_string_ac_spec_returns_well_defined_result() -> None:
    """Empty string ac_spec → passed=False with a descriptive detail (no crash)."""
    result = bf_6_characterization_ac_kind_approval_test_diffs_legacy("")
    assert isinstance(result, dict)
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# Invalid input — must raise ValueError
# ---------------------------------------------------------------------------


def test_invalid_string_raises_value_error() -> None:
    """Non-characterization string raises ValueError."""
    with pytest.raises(ValueError):
        bf_6_characterization_ac_kind_approval_test_diffs_legacy("this is not an ac")


def test_invalid_dict_missing_characterization_key_raises_value_error() -> None:
    """Dict without 'characterization' key raises ValueError."""
    with pytest.raises(ValueError):
        bf_6_characterization_ac_kind_approval_test_diffs_legacy(
            {"pytest": "tests/test_something.py"}
        )


def test_invalid_phase_raises_value_error() -> None:
    """Unrecognised phase raises ValueError."""
    with pytest.raises(ValueError, match="phase"):
        bf_6_characterization_ac_kind_approval_test_diffs_legacy(
            None, phase="invalid_phase"
        )


# ---------------------------------------------------------------------------
# parse_characterization_ac (kinds.py)
# ---------------------------------------------------------------------------


def test_parse_characterization_ac_from_dict() -> None:
    """parse_characterization_ac handles the dict form correctly."""
    raw = {
        "characterization": {
            "target": "src/foo/bar.py::Bar.method",
            "sample_inputs": [[1], [2]],
            "snapshot_dir": "tests/snapshots/test_bf6/",
        }
    }
    ac = parse_characterization_ac(raw)
    assert ac is not None
    assert isinstance(ac, CharacterizationAC)
    assert ac.target == "src/foo/bar.py::Bar.method"
    assert ac.snapshot_dir == "tests/snapshots/test_bf6/"


def test_parse_characterization_ac_from_string() -> None:
    """parse_characterization_ac handles the inline string form."""
    ac = parse_characterization_ac("characterization: src/foo/bar.py::Bar.method")
    assert ac is not None
    assert ac.target == "src/foo/bar.py::Bar.method"
    assert ac.sample_inputs == "auto"


def test_parse_characterization_ac_returns_none_for_non_ac() -> None:
    """parse_characterization_ac returns None for non-matching input."""
    assert parse_characterization_ac("pytest: tests/test_foo.py") is None
    assert parse_characterization_ac({"pytest": "tests/test_foo.py"}) is None
    assert parse_characterization_ac(42) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Observer phase (observe_and_snapshot)
# ---------------------------------------------------------------------------


def test_observe_and_snapshot_writes_files(tmp_path: pathlib.Path) -> None:
    """observe_and_snapshot creates snapshot files for Bar.method."""
    # Create the foo/bar.py structure in tmp_path so the resolver can find it
    foo_dir = tmp_path / "src" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "__init__.py").write_text("")
    bar_src = pathlib.Path(__file__).parent.parent / "src" / "foo" / "bar.py"
    (foo_dir / "bar.py").write_text(bar_src.read_text())

    ac = CharacterizationAC(
        target="src/foo/bar.py::bar_method",
        sample_inputs=[[0], [1], [5]],
        snapshot_dir="tests/snapshots/bf6_observer/",
    )

    result = observe_and_snapshot(ac, tmp_path)
    assert isinstance(result, SnapshotResult)
    assert result.success, f"Observer errors: {result.errors}"
    assert len(result.snapshot_files) == 3
    for snap_file in result.snapshot_files:
        assert snap_file.exists()
        content = snap_file.read_text()
        assert "RETURN:" in content


def test_observe_snapshot_zero_input_does_not_crash(tmp_path: pathlib.Path) -> None:
    """observe_and_snapshot with (0,) input succeeds and captures output."""
    foo_dir = tmp_path / "src" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "__init__.py").write_text("")
    bar_src = pathlib.Path(__file__).parent.parent / "src" / "foo" / "bar.py"
    (foo_dir / "bar.py").write_text(bar_src.read_text())

    ac = CharacterizationAC(
        target="src/foo/bar.py::bar_method",
        sample_inputs=[[0]],
        snapshot_dir="tests/snapshots/bf6_zero/",
    )

    result = observe_and_snapshot(ac, tmp_path)
    assert result.success
    content = result.snapshot_files[0].read_text()
    assert "result=0" in content


# ---------------------------------------------------------------------------
# Verifier phase (verify_against_snapshots)
# ---------------------------------------------------------------------------


def test_verify_passes_when_behavior_unchanged(tmp_path: pathlib.Path) -> None:
    """verify_against_snapshots passes when current output equals baseline."""
    foo_dir = tmp_path / "src" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "__init__.py").write_text("")
    bar_src = pathlib.Path(__file__).parent.parent / "src" / "foo" / "bar.py"
    (foo_dir / "bar.py").write_text(bar_src.read_text())

    ac = CharacterizationAC(
        target="src/foo/bar.py::bar_method",
        sample_inputs=[[2], [4]],
        snapshot_dir="tests/snapshots/bf6_verify_pass/",
    )

    # Observer phase first
    obs = observe_and_snapshot(ac, tmp_path)
    assert obs.success

    # Verifier phase — same code, same output
    ver: VerificationResult = verify_against_snapshots(ac, tmp_path)
    assert ver.passed, f"Expected pass but got diffs: {ver.diffs}"


def test_verify_fails_when_behavior_changes(tmp_path: pathlib.Path) -> None:
    """verify_against_snapshots fails when current output differs from snapshot."""
    foo_dir = tmp_path / "src" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "__init__.py").write_text("")
    bar_src = pathlib.Path(__file__).parent.parent / "src" / "foo" / "bar.py"
    (foo_dir / "bar.py").write_text(bar_src.read_text())

    ac = CharacterizationAC(
        target="src/foo/bar.py::bar_method",
        sample_inputs=[[3]],
        snapshot_dir="tests/snapshots/bf6_verify_fail/",
    )

    # Observer phase
    obs = observe_and_snapshot(ac, tmp_path)
    assert obs.success

    # Mutate the target so behavior changes
    changed_src = bar_src.read_text().replace("value * 2", "value * 3")
    (foo_dir / "bar.py").write_text(changed_src)

    ver: VerificationResult = verify_against_snapshots(ac, tmp_path)
    assert not ver.passed
    assert len(ver.diffs) > 0


def test_verify_fails_when_snapshot_dir_missing(tmp_path: pathlib.Path) -> None:
    """verify_against_snapshots fails gracefully when no snapshots exist."""
    ac = CharacterizationAC(
        target="src/foo/bar.py::bar_method",
        sample_inputs=[[1]],
        snapshot_dir="tests/snapshots/nonexistent/",
    )
    ver = verify_against_snapshots(ac, tmp_path)
    assert not ver.passed
    assert "not exist" in ver.details.lower() or "not found" in ver.details.lower() or ver.details


# ---------------------------------------------------------------------------
# Integration via the main dispatcher
# ---------------------------------------------------------------------------


def test_dispatcher_observe_phase_succeeds(tmp_path: pathlib.Path) -> None:
    """Dispatcher in observe phase writes snapshots and returns passed=True."""
    foo_dir = tmp_path / "src" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "__init__.py").write_text("")
    bar_src = pathlib.Path(__file__).parent.parent / "src" / "foo" / "bar.py"
    (foo_dir / "bar.py").write_text(bar_src.read_text())

    ac_spec = {
        "characterization": {
            "target": "src/foo/bar.py::Bar.method",
            "sample_inputs": [[0], [1]],
            "snapshot_dir": "tests/snapshots/bf6_dispatch_obs/",
        }
    }
    result = bf_6_characterization_ac_kind_approval_test_diffs_legacy(
        ac_spec, workspace=tmp_path, phase="observe"
    )
    assert result["passed"] is True
    assert result["phase"] == "observe"


def test_dispatcher_verify_phase_passes_unchanged(tmp_path: pathlib.Path) -> None:
    """Dispatcher in verify phase passes when behavior unchanged."""
    foo_dir = tmp_path / "src" / "foo"
    foo_dir.mkdir(parents=True)
    (foo_dir / "__init__.py").write_text("")
    bar_src = pathlib.Path(__file__).parent.parent / "src" / "foo" / "bar.py"
    (foo_dir / "bar.py").write_text(bar_src.read_text())

    ac_spec = {
        "characterization": {
            "target": "src/foo/bar.py::Bar.method",
            "sample_inputs": [[7]],
            "snapshot_dir": "tests/snapshots/bf6_dispatch_ver/",
        }
    }
    # Observe first
    bf_6_characterization_ac_kind_approval_test_diffs_legacy(
        ac_spec, workspace=tmp_path, phase="observe"
    )
    # Verify
    result = bf_6_characterization_ac_kind_approval_test_diffs_legacy(
        ac_spec, workspace=tmp_path, phase="verify"
    )
    assert result["passed"] is True
    assert result["phase"] == "verify"
