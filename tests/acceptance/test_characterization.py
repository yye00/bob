"""Tests for bob.acceptance.characterization module (BF-6).

Verifies that:
- CharacterizationAC is importable from bob.acceptance.characterization.
- All public helpers are accessible from the characterization sub-module.
- The module correctly re-exports from bob.acceptance.kinds.
- parse_characterization_ac / observe_and_snapshot / verify_against_snapshots
  work identically when imported from either path.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

import bob.acceptance.characterization as char_mod
from bob.acceptance.characterization import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


# ---------------------------------------------------------------------------
# Import / existence checks
# ---------------------------------------------------------------------------


class TestCharacterizationModuleImports:
    def test_characterization_ac_importable(self):
        assert CharacterizationAC is not None

    def test_snapshot_result_importable(self):
        assert SnapshotResult is not None

    def test_verification_result_importable(self):
        assert VerificationResult is not None

    def test_parse_characterization_ac_callable(self):
        assert callable(parse_characterization_ac)

    def test_observe_and_snapshot_callable(self):
        assert callable(observe_and_snapshot)

    def test_verify_against_snapshots_callable(self):
        assert callable(verify_against_snapshots)

    def test_module_all_exports_characterization_ac(self):
        assert "CharacterizationAC" in char_mod.__all__

    def test_same_class_as_kinds(self):
        from bob.acceptance.kinds import CharacterizationAC as KindsAC
        assert CharacterizationAC is KindsAC


# ---------------------------------------------------------------------------
# Functional smoke tests (via characterization module path)
# ---------------------------------------------------------------------------


class TestCharacterizationModuleFunctions:
    def test_parse_returns_characterization_ac_instance(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "src/foo/bar.py::bar_method",
                    "sample_inputs": [[1]],
                    "snapshot_dir": "tests/snapshots/smoke/",
                }
            }
        )
        assert isinstance(ac, CharacterizationAC)
        assert ac.target == "src/foo/bar.py::bar_method"

    def test_parse_returns_none_for_non_characterization(self):
        result = parse_characterization_ac("pytest: tests/test_foo.py")
        assert result is None

    def test_observe_creates_snapshot_files(self, tmp_path):
        target_file = tmp_path / "mod.py"
        target_file.write_text(
            textwrap.dedent("def compute(x): return x * 3\n"),
            encoding="utf-8",
        )
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::compute",
                    "sample_inputs": [[5]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)
        assert result.success
        assert len(result.snapshot_files) == 1

    def test_verify_passes_for_unchanged_function(self, tmp_path):
        target_file = tmp_path / "mod.py"
        target_file.write_text(
            textwrap.dedent("def value(): return 42\n"),
            encoding="utf-8",
        )
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::value",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)
        assert result.passed

    def test_verify_fails_for_changed_function(self, tmp_path):
        target_file = tmp_path / "mod.py"
        target_file.write_text(
            textwrap.dedent("def value(): return 42\n"),
            encoding="utf-8",
        )
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::value",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        target_file.write_text(
            textwrap.dedent("def value(): return 99\n"),
            encoding="utf-8",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert len(result.diffs) > 0


# ---------------------------------------------------------------------------
# Integration: bob.acceptance.kinds and bob.acceptance.characterization
# are the same underlying types
# ---------------------------------------------------------------------------


class TestKindsCharacterizationIntegration:
    def test_kinds_module_importable(self):
        from bob.acceptance import kinds  # noqa: F401

    def test_characterization_ac_from_kinds_is_same(self):
        from bob.acceptance.kinds import CharacterizationAC as KindsAC
        from bob.acceptance.characterization import CharacterizationAC as CharAC
        assert KindsAC is CharAC

    def test_parse_function_is_identical(self):
        from bob.acceptance.kinds import parse_characterization_ac as kinds_fn
        from bob.acceptance.characterization import parse_characterization_ac as char_fn
        assert kinds_fn is char_fn
