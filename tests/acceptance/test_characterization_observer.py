"""Tests for CharacterizationObserver (observe_and_snapshot) — BF-6.

Verifies the observer phase of the characterization AC kind:
- CharacterizationObserver is importable from bob3.acceptance.characterization.
- observe_and_snapshot writes snapshot files for each input.
- Snapshot files contain stdout, return value, and args header.
- 'auto' sample_inputs produce a single no-arg snapshot.
- Multi-input lists produce one snapshot file per input.
- Bad target produces a failure SnapshotResult (not an exception).
- Empty sample_inputs list yields success with no files written.
- Snapshot directory is created automatically.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.acceptance.characterization import CharacterizationObserver
from bob3.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    observe_and_snapshot,
    parse_characterization_ac,
)


# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------


class TestCharacterizationObserverImport:
    def test_observer_importable_from_characterization_module(self):
        assert CharacterizationObserver is not None

    def test_observer_is_callable(self):
        assert callable(CharacterizationObserver)

    def test_observer_is_observe_and_snapshot(self):
        assert CharacterizationObserver is observe_and_snapshot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: pathlib.Path, source: str, filename: str = "mod.py") -> pathlib.Path:
    """Write *source* to tmp_path/<filename> and return the workspace root."""
    (tmp_path / filename).write_text(textwrap.dedent(source), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Basic snapshot creation
# ---------------------------------------------------------------------------


class TestObserveAndSnapshotBasic:
    def test_returns_snapshot_result_instance(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)

    def test_success_true_for_valid_target(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True

    def test_snapshot_file_created(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert len(result.snapshot_files) == 1

    def test_snapshot_file_path_exists_on_disk(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        for f in result.snapshot_files:
            assert f.exists()

    def test_snapshot_dir_created_automatically(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        snap_dir = tmp_path / "snapshots" / "new"
        assert not snap_dir.exists()
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/new/",
        )
        observe_and_snapshot(ac, tmp_path)
        assert snap_dir.exists()


# ---------------------------------------------------------------------------
# Snapshot content
# ---------------------------------------------------------------------------


class TestSnapshotContent:
    def test_snapshot_contains_return_value(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 'hello'\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        content = result.snapshot_files[0].read_text()
        assert "hello" in content

    def test_snapshot_contains_args_header(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        content = result.snapshot_files[0].read_text()
        assert "ARGS:" in content

    def test_snapshot_contains_return_label(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 99\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        content = result.snapshot_files[0].read_text()
        assert "RETURN:" in content

    def test_snapshot_captures_stdout(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): print('output'); return None\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        content = result.snapshot_files[0].read_text()
        assert "output" in content
        assert "STDOUT:" in content


# ---------------------------------------------------------------------------
# Multiple sample inputs
# ---------------------------------------------------------------------------


class TestMultipleInputs:
    def test_one_snapshot_per_input(self, tmp_path):
        _make_workspace(tmp_path, "def double(x): return x * 2\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::double",
                    "sample_inputs": [[1], [2], [3]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert len(result.snapshot_files) == 3

    def test_no_errors_for_valid_inputs(self, tmp_path):
        _make_workspace(tmp_path, "def double(x): return x * 2\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::double",
                    "sample_inputs": [[0], [5]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.errors == []


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


class TestEmptyInputs:
    def test_empty_sample_inputs_list_succeeds(self, tmp_path):
        _make_workspace(tmp_path, "def fn(x): return x\n")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs=[],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True

    def test_empty_sample_inputs_no_files_written(self, tmp_path):
        _make_workspace(tmp_path, "def fn(x): return x\n")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs=[],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.snapshot_files == []

    def test_empty_sample_inputs_no_errors(self, tmp_path):
        _make_workspace(tmp_path, "def fn(x): return x\n")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs=[],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.errors == []


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestObserveErrors:
    def test_bad_target_returns_failure_not_exception(self, tmp_path):
        ac = CharacterizationAC(
            target="nonexistent_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)
        assert result.success is False

    def test_bad_target_has_error_message(self, tmp_path):
        ac = CharacterizationAC(
            target="nonexistent_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert len(result.errors) > 0

    def test_snapshot_files_empty_on_failure(self, tmp_path):
        ac = CharacterizationAC(
            target="nonexistent_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.snapshot_files == []

    def test_exception_raising_callable_captured_not_raised(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): raise RuntimeError('boom')\n")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        content = result.snapshot_files[0].read_text()
        assert "EXCEPTION" in content or "RuntimeError" in content
