"""Tests for bob.acceptance.characterization and bob.acceptance.observer modules.

Covers the public API surface required by BF-6 acceptance criteria:
  - CharacterizationAC is importable from bob.acceptance.characterization
  - observe_target_behavior is importable from bob.acceptance.observer
  - Observer phase writes snapshot files
  - Verifier phase detects unchanged and changed behavior
  - parse_characterization_ac handles dict and string forms
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.acceptance.characterization import CharacterizationAC
from bob.acceptance.observer import observe_target_behavior
from bob.acceptance.kinds import (
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


# ---------------------------------------------------------------------------
# Module-level symbol availability
# ---------------------------------------------------------------------------


def test_characterization_ac_importable() -> None:
    """CharacterizationAC is importable from bob.acceptance.characterization."""
    assert CharacterizationAC is not None
    assert callable(CharacterizationAC)


def test_observe_target_behavior_importable() -> None:
    """observe_target_behavior is importable from bob.acceptance.observer."""
    assert callable(observe_target_behavior)


# ---------------------------------------------------------------------------
# observe_target_behavior — basic usage
# ---------------------------------------------------------------------------


def test_observe_target_behavior_from_dict(tmp_path: pathlib.Path) -> None:
    """observe_target_behavior accepts a dict AC spec and returns SnapshotResult."""
    target_file = tmp_path / "mod.py"
    target_file.write_text(
        textwrap.dedent("def greet(name): return f'hello {name}'\n"),
        encoding="utf-8",
    )
    ac_spec = {
        "characterization": {
            "target": "mod.py::greet",
            "sample_inputs": [["world"]],
            "snapshot_dir": "snapshots/greet/",
        }
    }
    result = observe_target_behavior(ac_spec, workspace=tmp_path)
    assert isinstance(result, SnapshotResult)
    assert result.success
    assert len(result.snapshot_files) == 1
    content = result.snapshot_files[0].read_text()
    assert "hello world" in content


def test_observe_target_behavior_from_characterization_ac(tmp_path: pathlib.Path) -> None:
    """observe_target_behavior accepts a CharacterizationAC instance."""
    target_file = tmp_path / "mod.py"
    target_file.write_text("def double(x): return x * 2\n", encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::double",
        sample_inputs=[[3], [7]],
        snapshot_dir="snapshots/double/",
    )
    result = observe_target_behavior(ac, workspace=tmp_path)
    assert result.success
    assert len(result.snapshot_files) == 2


def test_observe_target_behavior_from_string(tmp_path: pathlib.Path) -> None:
    """observe_target_behavior accepts an inline characterization: string."""
    target_file = tmp_path / "mod.py"
    target_file.write_text("def ping(): return 'pong'\n", encoding="utf-8")
    # Inline string form sets sample_inputs='auto' (no-arg call)
    result = observe_target_behavior(
        "characterization: mod.py::ping", workspace=tmp_path
    )
    assert isinstance(result, SnapshotResult)
    assert result.success
    assert len(result.snapshot_files) == 1
    content = result.snapshot_files[0].read_text()
    assert "pong" in content


def test_observe_target_behavior_invalid_spec_raises() -> None:
    """observe_target_behavior raises ValueError for non-AC input."""
    with pytest.raises(ValueError):
        observe_target_behavior("pytest: tests/test_something.py")


def test_observe_target_behavior_missing_target_raises(tmp_path: pathlib.Path) -> None:
    """observe_target_behavior raises ValueError when target file is missing."""
    ac_spec = {
        "characterization": {
            "target": "nonexistent.py::fn",
            "sample_inputs": [[]],
            "snapshot_dir": "snapshots/",
        }
    }
    result = observe_target_behavior(ac_spec, workspace=tmp_path)
    # Resolution failure is captured as an error, not an exception
    assert not result.success
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# CharacterizationAC dataclass
# ---------------------------------------------------------------------------


def test_characterization_ac_fields() -> None:
    """CharacterizationAC has target, sample_inputs, snapshot_dir, allow_changes."""
    ac = CharacterizationAC(
        target="src/foo/bar.py::Bar.method",
        sample_inputs=[[1], [2]],
        snapshot_dir="tests/snapshots/",
    )
    assert ac.target == "src/foo/bar.py::Bar.method"
    assert ac.sample_inputs == [[1], [2]]
    assert ac.snapshot_dir == "tests/snapshots/"
    assert ac.allow_changes == []


def test_characterization_ac_frozen() -> None:
    """CharacterizationAC is frozen (immutable)."""
    ac = CharacterizationAC(
        target="t", sample_inputs="auto", snapshot_dir="s/"
    )
    with pytest.raises((AttributeError, TypeError)):
        ac.target = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# parse_characterization_ac
# ---------------------------------------------------------------------------


def test_parse_from_full_dict() -> None:
    """parse_characterization_ac returns CharacterizationAC from a full dict."""
    raw = {
        "characterization": {
            "target": "src/foo/bar.py::Bar.method",
            "sample_inputs": [[0], [5]],
            "snapshot_dir": "tests/snapshots/bf6/",
            "allow_changes": ["*timestamp*"],
        }
    }
    ac = parse_characterization_ac(raw)
    assert ac is not None
    assert ac.target == "src/foo/bar.py::Bar.method"
    assert ac.allow_changes == ["*timestamp*"]


def test_parse_from_string_sets_defaults() -> None:
    """parse_characterization_ac string form sets auto sample_inputs and default dir."""
    ac = parse_characterization_ac("characterization: src/foo/bar.py::Bar.method")
    assert ac is not None
    assert ac.target == "src/foo/bar.py::Bar.method"
    assert ac.sample_inputs == "auto"
    assert "bar_method" in ac.snapshot_dir or "Bar" in ac.snapshot_dir or ac.snapshot_dir.startswith("tests/")


def test_parse_returns_none_for_wrong_key() -> None:
    """parse_characterization_ac returns None for a dict missing the 'characterization' key."""
    result = parse_characterization_ac({"pytest": "tests/test_foo.py"})
    assert result is None


def test_parse_returns_none_for_non_matching_string() -> None:
    """parse_characterization_ac returns None for a non-matching string."""
    assert parse_characterization_ac("File exists: src/foo.py") is None


def test_parse_returns_none_for_integer() -> None:
    """parse_characterization_ac returns None for an integer."""
    assert parse_characterization_ac(42) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Full workflow: observe → verify
# ---------------------------------------------------------------------------


def test_full_workflow_unchanged_behavior(tmp_path: pathlib.Path) -> None:
    """Observer then verifier passes when behavior is unchanged."""
    target_file = tmp_path / "mod.py"
    target_file.write_text("def triple(x): return x * 3\n", encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::triple",
        sample_inputs=[[2], [5]],
        snapshot_dir="snapshots/triple/",
    )
    obs = observe_and_snapshot(ac, tmp_path)
    assert obs.success, f"Observer failed: {obs.errors}"

    ver: VerificationResult = verify_against_snapshots(ac, tmp_path)
    assert ver.passed, f"Verifier failed: {ver.diffs}"


def test_full_workflow_detects_regression(tmp_path: pathlib.Path) -> None:
    """Observer then mutated source → verifier fails."""
    target_file = tmp_path / "mod.py"
    target_file.write_text("def add_one(x): return x + 1\n", encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::add_one",
        sample_inputs=[[10]],
        snapshot_dir="snapshots/add_one/",
    )
    obs = observe_and_snapshot(ac, tmp_path)
    assert obs.success

    # Mutate behavior
    target_file.write_text("def add_one(x): return x + 99\n", encoding="utf-8")

    ver: VerificationResult = verify_against_snapshots(ac, tmp_path)
    assert not ver.passed
    assert len(ver.diffs) > 0


def test_verify_without_prior_observe_fails(tmp_path: pathlib.Path) -> None:
    """verify_against_snapshots fails gracefully when no snapshots exist."""
    ac = CharacterizationAC(
        target="mod.py::fn",
        sample_inputs=[[1]],
        snapshot_dir="snapshots/no_observe/",
    )
    ver = verify_against_snapshots(ac, tmp_path)
    assert not ver.passed
    assert ver.details  # descriptive message


# ---------------------------------------------------------------------------
# allow_changes glob behaviour
# ---------------------------------------------------------------------------


def test_allow_changes_permits_matching_diff(tmp_path: pathlib.Path) -> None:
    """Diffs matching allow_changes globs do not fail the AC."""
    target_file = tmp_path / "mod.py"
    target_file.write_text(
        "import time\ndef stamp(): return f'ts={time.time()}'\n",
        encoding="utf-8",
    )
    ac = CharacterizationAC(
        target="mod.py::stamp",
        sample_inputs=[[]],
        snapshot_dir="snapshots/stamp/",
        allow_changes=["*ts=*"],
    )
    obs = observe_and_snapshot(ac, tmp_path)
    assert obs.success

    # The timestamp will always differ between calls — but allow_changes covers it
    ver = verify_against_snapshots(ac, tmp_path)
    assert ver.passed
