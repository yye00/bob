"""Tests for BF-6 — Characterization AC kind (approval-test diffs for legacy code).

Covers:
  - parse_characterization_ac: dict form, string form, None/invalid inputs
  - observe_and_snapshot: target resolution, snapshot file creation, error handling
  - verify_against_snapshots: pass on unchanged, fail on regression, allow_changes globs
  - CharacterizationAC dataclass fields
  - observe_target / verify_snapshot_diff aliases in bob.acceptance.characterization
  - orchestrator integration: bob.acceptance registry has 'characterization' kind
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)
from bob.acceptance.characterization import (
    observe_target,
    verify_snapshot_diff,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_target(tmp_path: pathlib.Path, source: str, filename: str = "target_mod.py") -> str:
    """Write *source* to tmp_path/<filename> and return the relative path."""
    f = tmp_path / filename
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return filename


# ---------------------------------------------------------------------------
# parse_characterization_ac
# ---------------------------------------------------------------------------


class TestParseCharacterizationAC:
    def test_dict_form_minimal(self):
        ac = parse_characterization_ac({
            "characterization": {
                "target": "src/foo/bar.py::Bar.method",
                "sample_inputs": "auto",
                "snapshot_dir": "tests/snapshots/test1/",
            }
        })
        assert ac is not None
        assert ac.target == "src/foo/bar.py::Bar.method"
        assert ac.sample_inputs == "auto"
        assert ac.snapshot_dir == "tests/snapshots/test1/"

    def test_dict_form_with_allow_changes(self):
        ac = parse_characterization_ac({
            "characterization": {
                "target": "src/foo/bar.py::bar_method",
                "sample_inputs": [[1], [2]],
                "snapshot_dir": "snapshots/",
                "allow_changes": ["*timestamp*"],
            }
        })
        assert ac is not None
        assert ac.allow_changes == ["*timestamp*"]

    def test_string_form_parsed_as_target(self):
        ac = parse_characterization_ac("characterization: src/foo/bar.py::bar_method")
        assert ac is not None
        assert ac.target == "src/foo/bar.py::bar_method"
        assert ac.sample_inputs == "auto"

    def test_none_returns_none(self):
        assert parse_characterization_ac(None) is None

    def test_irrelevant_string_returns_none(self):
        assert parse_characterization_ac("pytest: tests/test_foo.py") is None

    def test_empty_string_returns_none(self):
        result = parse_characterization_ac("")
        # Empty string doesn't match characterization prefix → None
        assert result is None

    def test_dict_without_characterization_key_returns_none(self):
        assert parse_characterization_ac({"behavior": "something"}) is None

    def test_dict_with_non_dict_body_returns_none(self):
        assert parse_characterization_ac({"characterization": "not a dict"}) is None

    def test_dict_with_empty_target_returns_none(self):
        assert parse_characterization_ac({"characterization": {"snapshot_dir": "s/"}}) is None

    def test_integer_returns_none(self):
        assert parse_characterization_ac(42) is None

    def test_default_snapshot_dir_generated_when_absent(self):
        ac = parse_characterization_ac({
            "characterization": {
                "target": "some.module.func",
                "sample_inputs": "auto",
            }
        })
        assert ac is not None
        assert "some" in ac.snapshot_dir

    def test_allow_changes_defaults_to_empty_list(self):
        ac = parse_characterization_ac({
            "characterization": {
                "target": "src/foo/bar.py::bar_method",
                "sample_inputs": "auto",
                "snapshot_dir": "s/",
            }
        })
        assert ac is not None
        assert ac.allow_changes == []


# ---------------------------------------------------------------------------
# CharacterizationAC dataclass
# ---------------------------------------------------------------------------


class TestCharacterizationACDataclass:
    def test_fields_present(self):
        ac = CharacterizationAC(
            target="mod.py::func",
            sample_inputs=[(1,), (2,)],
            snapshot_dir="snaps/",
        )
        assert ac.target == "mod.py::func"
        assert ac.sample_inputs == [(1,), (2,)]
        assert ac.snapshot_dir == "snaps/"
        assert ac.allow_changes == []

    def test_frozen_immutable(self):
        ac = CharacterizationAC(
            target="x", sample_inputs="auto", snapshot_dir="s/"
        )
        with pytest.raises((AttributeError, TypeError)):
            ac.target = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# observe_and_snapshot
# ---------------------------------------------------------------------------


class TestObserveAndSnapshot:
    def test_creates_snapshot_file(self, tmp_path):
        _write_target(tmp_path, "def double(x): return x * 2\n")
        ac = CharacterizationAC(
            target="target_mod.py::double",
            sample_inputs=[[3]],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert len(result.snapshot_files) == 1
        content = result.snapshot_files[0].read_text()
        assert "6" in content  # 3*2

    def test_snapshot_contains_args_header(self, tmp_path):
        _write_target(tmp_path, "def f(x): return x\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=[[42]],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        content = result.snapshot_files[0].read_text()
        assert "ARGS:" in content

    def test_multiple_inputs_create_multiple_snapshots(self, tmp_path):
        _write_target(tmp_path, "def f(x): return x\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=[[1], [2], [3]],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert len(result.snapshot_files) == 3

    def test_auto_inputs_creates_one_snapshot(self, tmp_path):
        _write_target(tmp_path, "def f(): return 'ok'\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert len(result.snapshot_files) == 1

    def test_empty_sample_inputs_list(self, tmp_path):
        _write_target(tmp_path, "def f(x): return x\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=[],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert result.snapshot_files == []
        assert result.errors == []

    def test_missing_target_file_returns_failure(self, tmp_path):
        ac = CharacterizationAC(
            target="nonexistent_mod.py::func",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is False
        assert len(result.errors) > 0

    def test_exception_in_target_captured_not_raised(self, tmp_path):
        _write_target(tmp_path, "def f(x):\n    raise RuntimeError('boom')\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=[[1]],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        # Exception is captured in snapshot, not propagated
        assert result.success is True
        content = result.snapshot_files[0].read_text()
        assert "EXCEPTION" in content or "RuntimeError" in content

    def test_snapshot_dir_created_automatically(self, tmp_path):
        _write_target(tmp_path, "def f(): return 1\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs="auto",
            snapshot_dir="nested/deep/snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert (tmp_path / "nested" / "deep" / "snapshots").exists()

    def test_stdout_captured_in_snapshot(self, tmp_path):
        _write_target(tmp_path, "def f():\n    print('hello from f')\n    return None\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        content = result.snapshot_files[0].read_text()
        assert "hello from f" in content

    def test_return_value_captured_in_snapshot(self, tmp_path):
        _write_target(tmp_path, "def f(x): return x * 10\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=[[5]],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        content = result.snapshot_files[0].read_text()
        assert "50" in content


# ---------------------------------------------------------------------------
# verify_against_snapshots
# ---------------------------------------------------------------------------


class TestVerifyAgainstSnapshots:
    def _setup_and_observe(
        self, tmp_path: pathlib.Path, source: str, inputs: list
    ) -> CharacterizationAC:
        _write_target(tmp_path, source)
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=inputs,
            snapshot_dir="snapshots/",
        )
        observe_and_snapshot(ac, tmp_path)
        return ac

    def test_unchanged_behavior_passes(self, tmp_path):
        ac = self._setup_and_observe(tmp_path, "def f(x): return x * 2\n", [[3]])
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True
        assert result.diffs == []

    def test_changed_behavior_fails(self, tmp_path):
        ac = self._setup_and_observe(tmp_path, "def f(x): return x * 2\n", [[3]])
        # Overwrite target with changed behavior
        (tmp_path / "target_mod.py").write_text("def f(x): return x * 3\n", encoding="utf-8")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert len(result.diffs) > 0

    def test_missing_snapshot_dir_fails(self, tmp_path):
        _write_target(tmp_path, "def f(x): return x\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs=[[1]],
            snapshot_dir="no_such_dir/",
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_missing_snapshot_file_fails(self, tmp_path):
        ac = self._setup_and_observe(tmp_path, "def f(x): return x\n", [[1], [2]])
        # Remove one snapshot
        (tmp_path / "snapshots" / "snapshot_0001.txt").unlink()
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_allow_changes_permits_matching_diff(self, tmp_path):
        # Behavior changes but the changed line matches allow_changes glob
        _write_target(tmp_path, "def f():\n    return 'timestamp=2024'\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
            allow_changes=["*timestamp*"],
        )
        observe_and_snapshot(ac, tmp_path)
        # Change the timestamp value
        (tmp_path / "target_mod.py").write_text(
            "def f():\n    return 'timestamp=2025'\n", encoding="utf-8"
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True

    def test_failed_result_has_details(self, tmp_path):
        ac = self._setup_and_observe(tmp_path, "def f(x): return x\n", [[1]])
        (tmp_path / "target_mod.py").write_text("def f(x): return x + 99\n", encoding="utf-8")
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result.details, str)
        assert len(result.details) > 0

    def test_passed_result_details_mentions_inputs(self, tmp_path):
        ac = self._setup_and_observe(tmp_path, "def f(x): return x\n", [[1]])
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True
        assert isinstance(result.details, str)

    def test_missing_target_after_observe_fails(self, tmp_path):
        ac = self._setup_and_observe(tmp_path, "def f(): return 1\n", "auto")
        (tmp_path / "target_mod.py").unlink()
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Aliases: observe_target, verify_snapshot_diff (from bob.acceptance.characterization)
# ---------------------------------------------------------------------------


class TestAliases:
    def test_observe_target_alias_works(self, tmp_path):
        _write_target(tmp_path, "def f(): return 42\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        result = observe_target(ac, tmp_path)
        assert isinstance(result, SnapshotResult)
        assert result.success is True

    def test_verify_snapshot_diff_alias_works(self, tmp_path):
        _write_target(tmp_path, "def f(): return 42\n")
        ac = CharacterizationAC(
            target="target_mod.py::f",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        observe_target(ac, tmp_path)
        result = verify_snapshot_diff(ac, tmp_path)
        assert isinstance(result, VerificationResult)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Orchestrator integration: registry has 'characterization' kind
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_registry_has_characterization_kind(self):
        from bob.acceptance.registry import get_ac_kind
        entry = get_ac_kind("characterization")
        assert entry is not None

    def test_registry_characterization_has_parser(self):
        from bob.acceptance.registry import get_ac_kind
        entry = get_ac_kind("characterization")
        assert callable(entry.get("parser"))

    def test_registry_characterization_has_observer(self):
        from bob.acceptance.registry import get_ac_kind
        entry = get_ac_kind("characterization")
        assert callable(entry.get("observer"))

    def test_registry_characterization_has_verifier(self):
        from bob.acceptance.registry import get_ac_kind
        entry = get_ac_kind("characterization")
        assert callable(entry.get("verifier"))

    def test_parse_via_registry_returns_characterization_ac(self):
        from bob.acceptance.registry import get_ac_kind
        entry = get_ac_kind("characterization")
        parser = entry["parser"]
        ac = parser({
            "characterization": {
                "target": "src/foo/bar.py::bar_method",
                "sample_inputs": "auto",
                "snapshot_dir": "s/",
            }
        })
        assert isinstance(ac, CharacterizationAC)

    def test_acceptance_kinds_importable(self):
        from bob.acceptance import kinds  # noqa: F401
        assert hasattr(kinds, "CharacterizationAC")
        assert hasattr(kinds, "parse_characterization_ac")
        assert hasattr(kinds, "observe_and_snapshot")
        assert hasattr(kinds, "verify_against_snapshots")
