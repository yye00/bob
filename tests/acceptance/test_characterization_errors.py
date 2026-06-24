"""Error-path tests for the characterization AC kind — BF-6.

Verifies that invalid or malformed characterization AC inputs are rejected
cleanly:
  - parse_characterization_ac returns None for unrecognized forms.
  - observe_and_snapshot returns SnapshotResult(success=False) for bad targets.
  - verify_against_snapshots returns VerificationResult(passed=False) for
    missing snapshot dirs or bad targets.
  - Neither function raises uncaught exceptions on invalid input.
"""

from __future__ import annotations

import pathlib

import pytest

from bob.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


# ---------------------------------------------------------------------------
# parse_characterization_ac error paths
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_none_returns_none(self):
        assert parse_characterization_ac(None) is None

    def test_integer_returns_none(self):
        assert parse_characterization_ac(42) is None

    def test_list_returns_none(self):
        assert parse_characterization_ac([1, 2, 3]) is None

    def test_unrelated_string_returns_none(self):
        assert parse_characterization_ac("File exists: src/foo.py") is None

    def test_empty_string_returns_none(self):
        assert parse_characterization_ac("") is None

    def test_dict_without_characterization_key_returns_none(self):
        assert parse_characterization_ac({"behavior": "something"}) is None

    def test_dict_with_non_dict_body_returns_none(self):
        assert parse_characterization_ac({"characterization": "plain string"}) is None

    def test_dict_with_numeric_body_returns_none(self):
        assert parse_characterization_ac({"characterization": 99}) is None

    def test_dict_with_empty_target_returns_none(self):
        result = parse_characterization_ac(
            {"characterization": {"target": "", "snapshot_dir": "s/"}}
        )
        assert result is None

    def test_dict_with_missing_target_returns_none(self):
        result = parse_characterization_ac(
            {"characterization": {"snapshot_dir": "s/"}}
        )
        assert result is None

    def test_valid_dict_returns_characterization_ac(self):
        result = parse_characterization_ac(
            {
                "characterization": {
                    "target": "src/foo/bar.py::bar_method",
                    "sample_inputs": "auto",
                    "snapshot_dir": "tests/snapshots/",
                }
            }
        )
        assert result is not None
        assert result.target == "src/foo/bar.py::bar_method"


# ---------------------------------------------------------------------------
# observe_and_snapshot error paths
# ---------------------------------------------------------------------------


class TestObserveErrors:
    def test_nonexistent_file_target_returns_snapshot_result(self, tmp_path):
        ac = CharacterizationAC(
            target="no_such_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)

    def test_nonexistent_file_target_success_is_false(self, tmp_path):
        ac = CharacterizationAC(
            target="no_such_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is False

    def test_nonexistent_file_target_has_errors(self, tmp_path):
        ac = CharacterizationAC(
            target="no_such_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert len(result.errors) > 0

    def test_nonexistent_file_target_snapshot_files_empty(self, tmp_path):
        ac = CharacterizationAC(
            target="no_such_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.snapshot_files == []

    def test_missing_attribute_returns_failure(self, tmp_path):
        (tmp_path / "mod.py").write_text("def fn(): return 1\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::nonexistent_func",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)
        assert result.success is False

    def test_does_not_raise_on_bad_target(self, tmp_path):
        ac = CharacterizationAC(
            target="completely_bogus_path/file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)


# ---------------------------------------------------------------------------
# verify_against_snapshots error paths
# ---------------------------------------------------------------------------


class TestVerifyErrors:
    def test_missing_snapshot_dir_returns_verification_result(self, tmp_path):
        (tmp_path / "mod.py").write_text("def fn(): return 1\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)

    def test_missing_snapshot_dir_passed_is_false(self, tmp_path):
        (tmp_path / "mod.py").write_text("def fn(): return 1\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_missing_snapshot_dir_has_details(self, tmp_path):
        (tmp_path / "mod.py").write_text("def fn(): return 1\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result.details, str)
        assert len(result.details) > 0

    def test_bad_target_with_existing_dir_returns_failure(self, tmp_path):
        (tmp_path / "snapshots").mkdir()
        ac = CharacterizationAC(
            target="no_such_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)
        assert result.passed is False

    def test_bad_target_verify_does_not_raise(self, tmp_path):
        (tmp_path / "snapshots").mkdir()
        ac = CharacterizationAC(
            target="completely_bogus/file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)

    def test_missing_individual_snapshot_fails(self, tmp_path):
        (tmp_path / "mod.py").write_text("def double(x): return x * 2\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::double",
            sample_inputs=[[1], [2]],
            snapshot_dir="snapshots/",
        )
        # Observe to create snapshots
        from bob.acceptance.kinds import observe_and_snapshot as obs
        obs(ac, tmp_path)
        # Remove one snapshot to simulate a missing file
        snap_dir = tmp_path / "snapshots"
        files = list(snap_dir.iterdir())
        assert len(files) > 0
        files[0].unlink()
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_verify_returns_diffs_empty_list_on_bad_target(self, tmp_path):
        (tmp_path / "snapshots").mkdir()
        ac = CharacterizationAC(
            target="no_such_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result.diffs, list)
