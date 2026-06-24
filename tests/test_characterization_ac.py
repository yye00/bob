"""Characterization AC kind tests — BF-6 main test entry point.

This file satisfies the ``pytest: tests/test_characterization_ac.py`` AC.
Full test coverage lives in ``test_bf_6_characterization_ac_kind_approval_test_diffs_legacy.py``
and ``test_acceptance_characterization.py``; this module runs a representative
subset via explicit imports so the AC file reference resolves to a real test.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.acceptance.characterization import CharacterizationAC, observe_phase
from bob.acceptance.kinds import (
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)
from bob.bf_6_characterization_ac_kind_approval_test_diffs_legacy import (
    bf_6_characterization_ac_kind_approval_test_diffs_legacy as dispatch,
    sample_inputs,
)
from foo.bar import Bar, bar_method


# ---------------------------------------------------------------------------
# Symbol availability
# ---------------------------------------------------------------------------


def test_characterization_ac_class_importable() -> None:
    assert CharacterizationAC is not None
    assert callable(CharacterizationAC)


def test_observe_phase_importable() -> None:
    assert callable(observe_phase)


def test_sample_inputs_importable() -> None:
    assert callable(sample_inputs)
    inputs = sample_inputs()
    assert isinstance(inputs, list)
    assert len(inputs) > 0


# ---------------------------------------------------------------------------
# parse_characterization_ac
# ---------------------------------------------------------------------------


def test_parse_from_dict_returns_characterization_ac() -> None:
    ac = parse_characterization_ac(
        {
            "characterization": {
                "target": "src/foo/bar.py::bar_method",
                "sample_inputs": [[1], [5]],
                "snapshot_dir": "tests/snapshots/test_parse/",
            }
        }
    )
    assert isinstance(ac, CharacterizationAC)
    assert ac.target == "src/foo/bar.py::bar_method"
    assert ac.snapshot_dir == "tests/snapshots/test_parse/"


def test_parse_from_string_returns_characterization_ac() -> None:
    ac = parse_characterization_ac("characterization: src/foo/bar.py::bar_method")
    assert isinstance(ac, CharacterizationAC)
    assert ac.target == "src/foo/bar.py::bar_method"
    assert ac.sample_inputs == "auto"


def test_parse_returns_none_for_unrelated_string() -> None:
    assert parse_characterization_ac("File exists: src/foo.py") is None


def test_parse_returns_none_for_none() -> None:
    assert parse_characterization_ac(None) is None


# ---------------------------------------------------------------------------
# observe_and_snapshot
# ---------------------------------------------------------------------------


def test_observe_and_snapshot_writes_files(tmp_path: pathlib.Path) -> None:
    target_file = tmp_path / "mod.py"
    target_file.write_text(textwrap.dedent("def double(x): return x * 2\n"), encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::double",
        sample_inputs=[[1], [2]],
        snapshot_dir="snaps/",
    )
    result = observe_and_snapshot(ac, tmp_path)
    assert isinstance(result, SnapshotResult)
    assert result.success is True
    assert len(result.snapshot_files) == 2


def test_observe_and_snapshot_content_contains_return(tmp_path: pathlib.Path) -> None:
    target_file = tmp_path / "mod.py"
    target_file.write_text(textwrap.dedent("def f(x): return x + 10\n"), encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::f",
        sample_inputs=[[5]],
        snapshot_dir="snaps/",
    )
    result = observe_and_snapshot(ac, tmp_path)
    content = result.snapshot_files[0].read_text()
    assert "15" in content


# ---------------------------------------------------------------------------
# verify_against_snapshots
# ---------------------------------------------------------------------------


def test_verify_passes_when_behavior_unchanged(tmp_path: pathlib.Path) -> None:
    target_file = tmp_path / "mod.py"
    target_file.write_text(textwrap.dedent("def f(x): return x * 2\n"), encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::f",
        sample_inputs=[[3]],
        snapshot_dir="snaps/",
    )
    observe_and_snapshot(ac, tmp_path)
    result = verify_against_snapshots(ac, tmp_path)
    assert isinstance(result, VerificationResult)
    assert result.passed is True


def test_verify_fails_when_behavior_changes(tmp_path: pathlib.Path) -> None:
    target_file = tmp_path / "mod.py"
    target_file.write_text(textwrap.dedent("def f(x): return x * 2\n"), encoding="utf-8")
    ac = CharacterizationAC(
        target="mod.py::f",
        sample_inputs=[[3]],
        snapshot_dir="snaps/",
    )
    observe_and_snapshot(ac, tmp_path)
    # Now change behavior
    target_file.write_text(textwrap.dedent("def f(x): return x * 3\n"), encoding="utf-8")
    result = verify_against_snapshots(ac, tmp_path)
    assert result.passed is False
    assert len(result.diffs) > 0


# ---------------------------------------------------------------------------
# Dispatcher — boundary and error
# ---------------------------------------------------------------------------


def test_dispatch_none_returns_failed_dict() -> None:
    result = dispatch(None)
    assert isinstance(result, dict)
    assert result["passed"] is False
    assert "detail" in result


def test_dispatch_invalid_string_raises_value_error() -> None:
    with pytest.raises(ValueError):
        dispatch("pytest: tests/test_foo.py")


def test_dispatch_invalid_phase_raises_value_error() -> None:
    with pytest.raises(ValueError, match="phase"):
        dispatch(
            {
                "characterization": {
                    "target": "src/foo/bar.py::bar_method",
                    "sample_inputs": [[1]],
                    "snapshot_dir": "tests/snapshots/disp_err/",
                }
            },
            phase="bad_phase",
        )


# ---------------------------------------------------------------------------
# foo.bar target
# ---------------------------------------------------------------------------


def test_bar_method_positive_returns_doubled() -> None:
    assert bar_method(4) == "result=8"


def test_bar_method_zero_boundary() -> None:
    assert bar_method(0) == "result=0"


def test_bar_method_negative_raises_value_error() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        bar_method(-1)
