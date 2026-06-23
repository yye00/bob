"""Tests for the characterization AC kind (BF-6) — approval-test diffs for legacy code.

This test file is the canonical AC-required test for the characterization AC kind.
It verifies:
- CharacterizationAC class is defined in bob3.acceptance.kinds
- parse_characterization_ac parses all supported AC forms
- observe_and_snapshot captures baseline behavior before changes
- verify_against_snapshots detects behavioral regressions after changes
- allow_changes glob patterns correctly suppress permitted diffs
- Integration: bob3.acceptance package exports the correct symbols
- The sample_inputs function is accessible in the module
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


# ---------------------------------------------------------------------------
# CharacterizationAC class
# ---------------------------------------------------------------------------


class TestCharacterizationACClass:
    def test_class_is_defined(self):
        assert CharacterizationAC is not None

    def test_can_instantiate(self):
        ac = CharacterizationAC(
            target="src/foo/bar.py::Bar.method",
            sample_inputs="auto",
            snapshot_dir="tests/snapshots/F-R7-601/",
        )
        assert ac.target == "src/foo/bar.py::Bar.method"
        assert ac.sample_inputs == "auto"
        assert ac.snapshot_dir == "tests/snapshots/F-R7-601/"

    def test_allow_changes_defaults_to_empty_list(self):
        ac = CharacterizationAC(
            target="mod.func",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        assert ac.allow_changes == []

    def test_is_frozen_dataclass(self):
        ac = CharacterizationAC(
            target="mod.func",
            sample_inputs="auto",
            snapshot_dir="snapshots/",
        )
        with pytest.raises((AttributeError, TypeError)):
            ac.target = "other"  # type: ignore[misc]

    def test_with_list_sample_inputs(self):
        ac = CharacterizationAC(
            target="src/foo/bar.py::Bar.method",
            sample_inputs=[[0], [1], [10]],
            snapshot_dir="tests/snapshots/test/",
            allow_changes=["*timestamp*"],
        )
        assert ac.sample_inputs == [[0], [1], [10]]
        assert ac.allow_changes == ["*timestamp*"]


# ---------------------------------------------------------------------------
# parse_characterization_ac
# ---------------------------------------------------------------------------


class TestParseCharacterizationAC:
    def test_parses_dict_form(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "src/foo/bar.py::Bar.method",
                    "sample_inputs": "auto",
                    "snapshot_dir": "tests/snapshots/F-R7-601/",
                }
            }
        )
        assert ac is not None
        assert isinstance(ac, CharacterizationAC)
        assert ac.target == "src/foo/bar.py::Bar.method"
        assert ac.snapshot_dir == "tests/snapshots/F-R7-601/"

    def test_parses_dict_form_with_list_inputs(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "bob3.mod.func",
                    "sample_inputs": [[0], [1], [10]],
                    "snapshot_dir": "tests/snapshots/x/",
                }
            }
        )
        assert ac is not None
        assert ac.sample_inputs == [[0], [1], [10]]

    def test_parses_dict_form_with_allow_changes(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.func",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                    "allow_changes": ["*timestamp*", "*date*"],
                }
            }
        )
        assert ac is not None
        assert ac.allow_changes == ["*timestamp*", "*date*"]

    def test_parses_inline_string_form(self):
        ac = parse_characterization_ac("characterization: src/foo/bar.py::Bar.method")
        assert ac is not None
        assert ac.target == "src/foo/bar.py::Bar.method"
        assert ac.sample_inputs == "auto"
        assert ac.snapshot_dir.startswith("tests/snapshots/")

    def test_returns_none_for_non_characterization_string(self):
        assert parse_characterization_ac("pytest: tests/test_foo.py") is None

    def test_returns_none_for_file_exists_string(self):
        assert parse_characterization_ac("File exists: src/foo.py") is None

    def test_returns_none_for_empty_string(self):
        assert parse_characterization_ac("") is None

    def test_returns_none_for_dict_without_characterization_key(self):
        assert parse_characterization_ac({"behavior": "X does Y"}) is None

    def test_returns_none_for_none_input(self):
        assert parse_characterization_ac(None) is None

    def test_returns_none_for_integer_input(self):
        assert parse_characterization_ac(42) is None

    def test_returns_none_for_missing_target(self):
        ac = parse_characterization_ac({"characterization": {"snapshot_dir": "s/"}})
        assert ac is None

    def test_returns_none_for_non_dict_body(self):
        ac = parse_characterization_ac({"characterization": "just a string"})
        assert ac is None

    def test_snapshot_dir_defaults_when_not_provided(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "src/foo/bar.py::Bar.method",
                    "sample_inputs": "auto",
                }
            }
        )
        assert ac is not None
        assert ac.snapshot_dir.startswith("tests/snapshots/")


# ---------------------------------------------------------------------------
# observe_and_snapshot (observer phase)
# ---------------------------------------------------------------------------


class TestObserveAndSnapshot:
    def test_returns_snapshot_result(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f(): return 1\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::f", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)

    def test_creates_snapshot_file(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f(): return 42\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::f", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        assert len(result.snapshot_files) == 1
        assert result.snapshot_files[0].exists()

    def test_snapshot_contains_return_value(self, tmp_path):
        (tmp_path / "mod.py").write_text("def greet(name): return f'hello {name}'\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::greet",
                    "sample_inputs": [["world"]],
                    "snapshot_dir": "snaps/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        content = result.snapshot_files[0].read_text()
        assert "hello world" in content
        assert "RETURN:" in content

    def test_snapshot_contains_args_header(self, tmp_path):
        (tmp_path / "mod.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::add",
                    "sample_inputs": [[1, 2]],
                    "snapshot_dir": "snaps/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        content = result.snapshot_files[0].read_text()
        assert "ARGS:" in content

    def test_creates_snapshot_dir_if_missing(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f(): return 1\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::f", "sample_inputs": "auto", "snapshot_dir": "deep/nested/"}}
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        assert (tmp_path / "deep/nested/").exists()

    def test_multiple_inputs_produce_multiple_files(self, tmp_path):
        (tmp_path / "mod.py").write_text("def double(x): return x * 2\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::double",
                    "sample_inputs": [[1], [2], [3]],
                    "snapshot_dir": "snaps/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        assert len(result.snapshot_files) == 3

    def test_bad_target_returns_failure(self, tmp_path):
        ac = parse_characterization_ac(
            {"characterization": {"target": "missing.py::f", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is False
        assert len(result.errors) > 0

    def test_exception_in_target_is_captured_not_propagated(self, tmp_path):
        (tmp_path / "mod.py").write_text("def boom(): raise ValueError('oops')\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::boom", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        content = result.snapshot_files[0].read_text()
        assert "EXCEPTION" in content


# ---------------------------------------------------------------------------
# verify_against_snapshots (verifier phase)
# ---------------------------------------------------------------------------


class TestVerifyAgainstSnapshots:
    def test_returns_verification_result(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f(): return 1\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::f", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)

    def test_passes_when_output_unchanged(self, tmp_path):
        (tmp_path / "mod.py").write_text("def greet(name): return f'hello {name}'\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::greet",
                    "sample_inputs": [["world"]],
                    "snapshot_dir": "snaps/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True
        assert result.diffs == []

    def test_fails_when_output_changes(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def greet(name): return f'hello {name}'\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::greet",
                    "sample_inputs": [["world"]],
                    "snapshot_dir": "snaps/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        target.write_text("def greet(name): return f'goodbye {name}'\n", encoding="utf-8")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert len(result.diffs) > 0

    def test_fails_when_snapshot_dir_missing(self, tmp_path):
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::f", "sample_inputs": "auto", "snapshot_dir": "nonexistent/"}}
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert "does not exist" in result.details

    def test_allow_changes_suppresses_matching_diffs(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def f(): return 'result: 2024-01-01'\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snaps/",
                    "allow_changes": ["*result*"],
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        target.write_text("def f(): return 'result: 2025-06-10'\n", encoding="utf-8")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True

    def test_allow_changes_does_not_suppress_unmatched_diffs(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def f(): return 'hello'\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snaps/",
                    "allow_changes": ["*timestamp*"],
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        target.write_text("def f(): return 'goodbye'\n", encoding="utf-8")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_details_contains_info_on_pass(self, tmp_path):
        (tmp_path / "mod.py").write_text("def f(): return 1\n", encoding="utf-8")
        ac = parse_characterization_ac(
            {"characterization": {"target": "mod.py::f", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed
        assert isinstance(result.details, str)
        assert len(result.details) > 0

    def test_bad_target_returns_failure(self, tmp_path):
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()
        ac = parse_characterization_ac(
            {"characterization": {"target": "missing.py::f", "sample_inputs": "auto", "snapshot_dir": "snaps/"}}
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert "Target resolution failed" in result.details


# ---------------------------------------------------------------------------
# Integration: bob3.acceptance package
# ---------------------------------------------------------------------------


class TestBob3AcceptanceIntegration:
    def test_package_importable(self):
        import bob3.acceptance  # noqa: F401

    def test_characterization_ac_exported_from_package(self):
        from bob3.acceptance import CharacterizationAC as AC
        assert AC is not None
        assert AC is CharacterizationAC

    def test_parse_function_exported_from_package(self):
        from bob3.acceptance import parse_characterization_ac as fn
        assert callable(fn)

    def test_kinds_module_importable(self):
        from bob3.acceptance import kinds  # noqa: F401

    def test_characterization_module_importable(self):
        from bob3.acceptance import characterization  # noqa: F401

    def test_all_public_symbols_importable_from_kinds(self):
        from bob3.acceptance.kinds import (
            CharacterizationAC,
            SnapshotResult,
            VerificationResult,
            observe_and_snapshot,
            parse_characterization_ac,
            verify_against_snapshots,
        )
        for sym in [CharacterizationAC, SnapshotResult, VerificationResult,
                    observe_and_snapshot, parse_characterization_ac, verify_against_snapshots]:
            assert sym is not None


# ---------------------------------------------------------------------------
# sample_inputs function
# ---------------------------------------------------------------------------


class TestSampleInputs:
    def test_sample_inputs_importable_from_foo_bar(self):
        from foo.bar import sample_inputs
        assert callable(sample_inputs)

    def test_sample_inputs_returns_list(self):
        from foo.bar import sample_inputs
        result = sample_inputs()
        assert isinstance(result, list)

    def test_sample_inputs_non_empty(self):
        from foo.bar import sample_inputs
        result = sample_inputs()
        assert len(result) > 0

    def test_sample_inputs_contains_zero_boundary(self):
        from foo.bar import sample_inputs
        result = sample_inputs()
        assert (0,) in result

    def test_sample_inputs_all_tuples(self):
        from foo.bar import sample_inputs
        result = sample_inputs()
        for item in result:
            assert isinstance(item, tuple)

    def test_sample_inputs_re_exported_from_bf6_module(self):
        from bob3.bf_6_characterization_ac_kind_approval_test_diffs_legacy import sample_inputs
        assert callable(sample_inputs)
