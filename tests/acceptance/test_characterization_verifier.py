"""Tests for CharacterizationVerifier (verify_against_snapshots) — BF-6.

Verifies the verifier phase of the characterization AC kind:
- CharacterizationVerifier is importable from bob.acceptance.characterization.
- verify_against_snapshots passes when behavior is unchanged.
- verify_against_snapshots fails when behavior changes.
- Diffs are returned when verification fails.
- allow_changes globs suppress permitted diffs.
- Missing snapshot_dir yields a failure (not an exception).
- Missing individual snapshot file yields a failure.
- Bad target yields a failure VerificationResult (not an exception).
- Multiple inputs are all verified against their respective snapshots.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.acceptance.characterization import CharacterizationVerifier
from bob.acceptance.kinds import (
    CharacterizationAC,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------


class TestCharacterizationVerifierImport:
    def test_verifier_importable_from_characterization_module(self):
        assert CharacterizationVerifier is not None

    def test_verifier_is_callable(self):
        assert callable(CharacterizationVerifier)

    def test_verifier_is_verify_against_snapshots(self):
        assert CharacterizationVerifier is verify_against_snapshots


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: pathlib.Path, source: str, filename: str = "mod.py") -> pathlib.Path:
    """Write *source* to tmp_path/<filename> and return the workspace root."""
    (tmp_path / filename).write_text(textwrap.dedent(source), encoding="utf-8")
    return tmp_path


def _make_ac(target: str, sample_inputs="auto", snapshot_dir: str = "snapshots/") -> CharacterizationAC:
    return parse_characterization_ac(
        {
            "characterization": {
                "target": target,
                "sample_inputs": sample_inputs,
                "snapshot_dir": snapshot_dir,
            }
        }
    )


# ---------------------------------------------------------------------------
# Pass cases
# ---------------------------------------------------------------------------


class TestVerifyPasses:
    def test_returns_verification_result_instance(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)

    def test_passes_when_output_unchanged(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True

    def test_no_diffs_when_output_unchanged(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert result.diffs == []

    def test_details_non_empty_on_pass(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result.details, str)
        assert len(result.details) > 0

    def test_passes_with_multiple_unchanged_inputs(self, tmp_path):
        _make_workspace(tmp_path, "def double(x): return x * 2\n")
        ac = _make_ac("mod.py::double", sample_inputs=[[1], [2], [3]])
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Fail cases
# ---------------------------------------------------------------------------


class TestVerifyFails:
    def test_fails_when_return_value_changes(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        (tmp_path / "mod.py").write_text("def fn(): return 99\n")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_diffs_non_empty_when_output_changes(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 42\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        (tmp_path / "mod.py").write_text("def fn(): return 99\n")
        result = verify_against_snapshots(ac, tmp_path)
        assert len(result.diffs) > 0

    def test_fails_when_stdout_changes(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): print('v1'); return None\n")
        ac = _make_ac("mod.py::fn")
        observe_and_snapshot(ac, tmp_path)
        (tmp_path / "mod.py").write_text("def fn(): print('v2'); return None\n")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_fails_when_snapshot_dir_missing(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        ac = _make_ac("mod.py::fn")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_details_present_when_dir_missing(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        ac = _make_ac("mod.py::fn")
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result.details, str)
        assert len(result.details) > 0

    def test_fails_when_individual_snapshot_file_missing(self, tmp_path):
        _make_workspace(tmp_path, "def double(x): return x * 2\n")
        ac = _make_ac("mod.py::double", sample_inputs=[[1], [2]])
        observe_and_snapshot(ac, tmp_path)
        snap_dir = tmp_path / "snapshots"
        for f in snap_dir.iterdir():
            f.unlink()
            break
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_bad_target_returns_failure_not_exception(self, tmp_path):
        (tmp_path / "snapshots").mkdir()
        ac = CharacterizationAC(
            target="nonexistent_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)
        assert result.passed is False

    def test_bad_target_has_details_message(self, tmp_path):
        (tmp_path / "snapshots").mkdir()
        ac = CharacterizationAC(
            target="nonexistent_file.py::fn",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert len(result.details) > 0


# ---------------------------------------------------------------------------
# allow_changes
# ---------------------------------------------------------------------------


class TestAllowChanges:
    def test_allow_changes_suppresses_matching_diff(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): print('timestamp=12345'); return None\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                    "allow_changes": ["*timestamp*"],
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        (tmp_path / "mod.py").write_text(
            "def fn(): print('timestamp=99999'); return None\n"
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True

    def test_allow_changes_does_not_suppress_unmatched_diff(self, tmp_path):
        _make_workspace(tmp_path, "def fn(): return 1\n")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::fn",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                    "allow_changes": ["*timestamp*"],
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        (tmp_path / "mod.py").write_text("def fn(): return 2\n")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
