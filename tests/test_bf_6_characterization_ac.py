"""Tests for BF-6 — Characterization AC kind (approval-test diffs for legacy code).

Covers the Feathers/Michael Hill characterization-test workflow:

  1. Parsing the ``characterization:`` AC body shape.
  2. Observer phase — capturing baseline snapshots before any edit.
  3. Verifier phase — passing when behavior is unchanged, failing on regression.
  4. ``allow_changes`` glob-permitted diffs.
  5. Dispatch entry point round-trips through observe → verify.
  6. Integration with ``bob.disk_reconciler`` (snapshot artifacts count toward
     AC satisfaction).
"""

from __future__ import annotations

import textwrap

import pytest

from bob.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    characterization,
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
# Parsing
# ---------------------------------------------------------------------------


class TestParseCharacterizationAC:
    def test_parses_full_dict_body(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "src/foo/bar.py::bar_method",
                    "sample_inputs": [[0], [1], [10]],
                    "snapshot_dir": "tests/snapshots/F-R7-601/",
                    "allow_changes": ["*timestamp*"],
                }
            }
        )
        assert isinstance(ac, CharacterizationAC)
        assert ac.target == "src/foo/bar.py::bar_method"
        assert ac.sample_inputs == [[0], [1], [10]]
        assert ac.snapshot_dir == "tests/snapshots/F-R7-601/"
        assert ac.allow_changes == ["*timestamp*"]

    def test_parses_inline_string_form(self):
        ac = parse_characterization_ac("characterization: pkg.mod::func")
        assert isinstance(ac, CharacterizationAC)
        assert ac.target == "pkg.mod::func"
        assert ac.sample_inputs == "auto"

    def test_defaults_snapshot_dir_when_omitted(self):
        ac = parse_characterization_ac(
            {"characterization": {"target": "src/foo/bar.py::bar_method"}}
        )
        assert ac is not None
        assert ac.snapshot_dir.startswith("tests/snapshots/")

    def test_returns_none_for_non_characterization_dict(self):
        assert parse_characterization_ac({"pytest": "tests/x.py"}) is None

    def test_returns_none_for_missing_target(self):
        assert (
            parse_characterization_ac({"characterization": {"sample_inputs": "auto"}})
            is None
        )


# ---------------------------------------------------------------------------
# Observer phase
# ---------------------------------------------------------------------------


class TestObserverPhase:
    def test_writes_one_snapshot_per_input(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def double(x): return x * 2\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::double",
                    "sample_inputs": [[0], [5]],
                    "snapshot_dir": "snaps/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)
        assert result.success is True
        assert len(result.snapshot_files) == 2
        assert (tmp_path / "snaps").is_dir()

    def test_snapshot_captures_return_value(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def double(x): return x * 2\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::double", sample_inputs=[[7]], snapshot_dir="snaps/"
        )
        result = observe_and_snapshot(ac, tmp_path)
        content = result.snapshot_files[0].read_text(encoding="utf-8")
        assert "14" in content  # 7 * 2

    def test_snapshot_captures_stdout(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text(
            "def talk(x):\n    print('hello', x)\n    return x\n", encoding="utf-8"
        )
        ac = CharacterizationAC(
            target="mod.py::talk", sample_inputs=[[3]], snapshot_dir="snaps/"
        )
        result = observe_and_snapshot(ac, tmp_path)
        content = result.snapshot_files[0].read_text(encoding="utf-8")
        assert "hello 3" in content

    def test_unresolvable_target_reports_failure_not_crash(self, tmp_path):
        ac = CharacterizationAC(
            target="does_not_exist.py::nope", sample_inputs=[[1]], snapshot_dir="s/"
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is False
        assert result.errors


# ---------------------------------------------------------------------------
# Verifier phase — the core characterization workflow
# ---------------------------------------------------------------------------


class TestVerifierPhase:
    def _write_target(self, tmp_path, body: str):
        target = tmp_path / "mod.py"
        target.write_text(body, encoding="utf-8")
        return CharacterizationAC(
            target="mod.py::compute", sample_inputs=[[2], [4]], snapshot_dir="snaps/"
        )

    def test_unchanged_behavior_passes(self, tmp_path):
        ac = self._write_target(tmp_path, "def compute(x): return x * 2\n")
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)
        assert result.passed is True
        assert result.diffs == []

    def test_regressed_behavior_fails_with_diff(self, tmp_path):
        ac = self._write_target(tmp_path, "def compute(x): return x * 2\n")
        observe_and_snapshot(ac, tmp_path)
        # Regress the target: now triples instead of doubles.
        (tmp_path / "mod.py").write_text(
            "def compute(x): return x * 3\n", encoding="utf-8"
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert result.diffs

    def test_missing_snapshot_dir_fails_gracefully(self, tmp_path):
        ac = self._write_target(tmp_path, "def compute(x): return x\n")
        # Never ran observer → no snapshot dir.
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_allow_changes_glob_permits_diff(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return 'v1'\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::compute",
            sample_inputs=[[1]],
            snapshot_dir="snaps/",
            allow_changes=["*v1*", "*v2*"],
        )
        observe_and_snapshot(ac, tmp_path)
        target.write_text("def compute(x): return 'v2'\n", encoding="utf-8")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# High-level dispatch entry points
# ---------------------------------------------------------------------------


class TestCharacterizationDispatch:
    def test_characterization_observe_then_verify(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return x + 1\n", encoding="utf-8")
        ac_body = {
            "characterization": {
                "target": "mod.py::compute",
                "sample_inputs": [[10]],
                "snapshot_dir": "snaps/",
            }
        }
        obs = characterization(ac_body, tmp_path, phase="observe")
        assert isinstance(obs, SnapshotResult)
        assert obs.success is True

        ver = characterization(ac_body, tmp_path, phase="verify")
        assert isinstance(ver, VerificationResult)
        assert ver.passed is True

    def test_characterization_invalid_phase_raises(self, tmp_path):
        with pytest.raises(ValueError):
            characterization(
                {"characterization": {"target": "mod.py::f"}}, tmp_path, phase="bad"
            )

    def test_dispatch_facade_full_cycle(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return x * 2\n", encoding="utf-8")
        spec = {
            "characterization": {
                "target": "mod.py::compute",
                "sample_inputs": [[3]],
                "snapshot_dir": "snaps/",
            }
        }
        obs = dispatch(spec, workspace=tmp_path, phase="observe")
        assert obs["passed"] is True

        ver = dispatch(spec, workspace=tmp_path, phase="verify")
        assert ver["passed"] is True
        assert ver["diffs"] == []

    def test_dispatch_detects_regression(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return x * 2\n", encoding="utf-8")
        spec = {
            "characterization": {
                "target": "mod.py::compute",
                "sample_inputs": [[3]],
                "snapshot_dir": "snaps/",
            }
        }
        dispatch(spec, workspace=tmp_path, phase="observe")
        target.write_text("def compute(x): return x * 99\n", encoding="utf-8")
        ver = dispatch(spec, workspace=tmp_path, phase="verify")
        assert ver["passed"] is False
        assert ver["diffs"]


# ---------------------------------------------------------------------------
# foo.bar concrete target
# ---------------------------------------------------------------------------


class TestFooBarTarget:
    def test_bar_method_doubles(self):
        assert Bar().method(4) == "result=8"

    def test_bar_method_negative_raises(self):
        with pytest.raises(ValueError):
            Bar().method(-1)

    def test_bar_function_wrapper(self):
        assert bar_method(5) == "result=10"

    def test_sample_inputs_shape(self):
        inputs = sample_inputs()
        assert isinstance(inputs, list)
        assert all(isinstance(t, tuple) for t in inputs)
        assert (0,) in inputs


# ---------------------------------------------------------------------------
# Integration: bob.disk_reconciler treats snapshots as AC-satisfaction artifacts
# ---------------------------------------------------------------------------


class TestDiskReconcilerIntegration:
    def test_disk_reconciler_module_importable(self):
        import bob.disk_reconciler as dr

        assert hasattr(dr, "reconcile_from_disk")
        assert hasattr(dr, "evaluate_ac_against_disk")

    def test_reconcile_passes_when_snapshots_present_and_match(self, tmp_path):
        from bob.acceptance.disk_reconciler import reconcile_characterization_ac

        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return x * 2\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::compute", sample_inputs=[[6]], snapshot_dir="snaps/"
        )
        observe_and_snapshot(ac, tmp_path)
        passed, detail = reconcile_characterization_ac(ac, tmp_path)
        assert passed is True
        assert "snapshot artifact" in detail

    def test_reconcile_fails_without_snapshots(self, tmp_path):
        from bob.acceptance.disk_reconciler import reconcile_characterization_ac

        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return x\n", encoding="utf-8")
        ac = CharacterizationAC(
            target="mod.py::compute", sample_inputs=[[1]], snapshot_dir="snaps/"
        )
        passed, detail = reconcile_characterization_ac(ac, tmp_path)
        assert passed is False

    def test_dispatch_reconcile_phase(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def compute(x): return x * 2\n", encoding="utf-8")
        spec = {
            "characterization": {
                "target": "mod.py::compute",
                "sample_inputs": [[8]],
                "snapshot_dir": "snaps/",
            }
        }
        dispatch(spec, workspace=tmp_path, phase="observe")
        rec = dispatch(spec, workspace=tmp_path, phase="reconcile")
        assert rec["passed"] is True
