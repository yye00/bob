"""Tests for the CharacterizationAC kind (BF-6 — approval-test diffs).

Covers:
- Parsing from dict (YAML mapping form) and string (inline form).
- parse_characterization_ac returns None for non-characterization inputs.
- CharacterizationAC dataclass is frozen and holds correct fields.
- observe_and_snapshot writes snapshot files to snapshot_dir.
- verify_against_snapshots passes when output is unchanged.
- verify_against_snapshots fails when output changes and no allow_changes match.
- allow_changes glob patterns suppress permitted diffs.
- Missing snapshot_dir causes verify_against_snapshots to fail with a clear message.
- Bad target raises descriptive error in SnapshotResult / VerificationResult.
- Bob3 acceptance package is importable (integration: bob3.acceptance).
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
# Helpers: build workspace fixtures with a simple target function
# ---------------------------------------------------------------------------


def _write_target(tmp_path: pathlib.Path, source: str, filename: str = "target_mod.py") -> pathlib.Path:
    """Write *source* to tmp_path/<filename> and return the path."""
    target_file = tmp_path / filename
    target_file.write_text(textwrap.dedent(source), encoding="utf-8")
    return target_file


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseCharacterizationAC:
    def test_returns_none_for_non_characterization_string(self):
        assert parse_characterization_ac("pytest: tests/test_foo.py") is None

    def test_returns_none_for_file_exists_string(self):
        assert parse_characterization_ac("File exists: src/foo.py") is None

    def test_returns_none_for_empty_string(self):
        assert parse_characterization_ac("") is None

    def test_returns_none_for_dict_without_characterization_key(self):
        assert parse_characterization_ac({"behavior": "X does Y when Z"}) is None

    def test_returns_none_for_non_dict_non_string(self):
        assert parse_characterization_ac(42) is None
        assert parse_characterization_ac(None) is None

    def test_parses_dict_form(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "src/foo/bar.py::Bar.method",
                    "sample_inputs": ["auto"],
                    "snapshot_dir": "tests/snapshots/F-R7-601/",
                }
            }
        )
        assert ac is not None
        assert isinstance(ac, CharacterizationAC)
        assert ac.target == "src/foo/bar.py::Bar.method"
        assert ac.snapshot_dir == "tests/snapshots/F-R7-601/"

    def test_parses_dict_form_with_allow_changes(self):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "bob3.mod.func",
                    "sample_inputs": [[]],
                    "snapshot_dir": "tests/snapshots/x/",
                    "allow_changes": ["*timestamp*"],
                }
            }
        )
        assert ac is not None
        assert ac.allow_changes == ["*timestamp*"]

    def test_parses_inline_string_form(self):
        ac = parse_characterization_ac("characterization: src/foo/bar.py::some_func")
        assert ac is not None
        assert ac.target == "src/foo/bar.py::some_func"
        assert ac.sample_inputs == "auto"

    def test_inline_string_sets_default_snapshot_dir(self):
        ac = parse_characterization_ac("characterization: mymod.func")
        assert ac is not None
        assert ac.snapshot_dir.startswith("tests/snapshots/")

    def test_dict_form_missing_target_returns_none(self):
        ac = parse_characterization_ac({"characterization": {"snapshot_dir": "tests/x/"}})
        assert ac is None

    def test_dict_form_non_dict_body_returns_none(self):
        ac = parse_characterization_ac({"characterization": "just a string"})
        assert ac is None

    def test_characterization_ac_is_frozen(self):
        ac = CharacterizationAC(
            target="mod.func",
            sample_inputs="auto",
            snapshot_dir="tests/snapshots/s/",
        )
        with pytest.raises((AttributeError, TypeError)):
            ac.target = "other"  # type: ignore[misc]

    def test_allow_changes_defaults_to_empty_list(self):
        ac = CharacterizationAC(
            target="mod.func",
            sample_inputs="auto",
            snapshot_dir="tests/snapshots/s/",
        )
        assert ac.allow_changes == []


# ---------------------------------------------------------------------------
# Snapshot (observer) phase tests
# ---------------------------------------------------------------------------


class TestObserveAndSnapshot:
    def test_snapshot_created_for_simple_function(self, tmp_path):
        _write_target(
            tmp_path,
            """
            def greet(name):
                return f"hello {name}"
            """,
        )
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::greet",
                    "sample_inputs": [["world"]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert isinstance(result, SnapshotResult)
        assert result.success is True
        assert len(result.snapshot_files) == 1
        snap = result.snapshot_files[0]
        assert snap.exists()
        content = snap.read_text()
        assert "hello world" in content

    def test_snapshot_contains_args_header(self, tmp_path):
        _write_target(tmp_path, "def add(a, b): return a + b")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::add",
                    "sample_inputs": [[1, 2]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        content = result.snapshot_files[0].read_text()
        assert "ARGS:" in content
        assert "RETURN:" in content

    def test_snapshot_dir_created_if_missing(self, tmp_path):
        _write_target(tmp_path, "def f(): return 42")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "deep/nested/snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        assert (tmp_path / "deep/nested/snapshots/").exists()

    def test_multiple_inputs_produce_multiple_snapshots(self, tmp_path):
        _write_target(tmp_path, "def double(x): return x * 2")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::double",
                    "sample_inputs": [[1], [2], [10]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        assert len(result.snapshot_files) == 3

    def test_bad_target_returns_failure(self, tmp_path):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "nonexistent_mod.py::no_func",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is False
        assert len(result.errors) > 0
        assert "Target resolution failed" in result.errors[0]

    def test_auto_sample_inputs_calls_with_no_args(self, tmp_path):
        _write_target(tmp_path, "def get_constant(): return 99")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::get_constant",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success
        content = result.snapshot_files[0].read_text()
        assert "99" in content

    def test_exception_in_target_captured_not_propagated(self, tmp_path):
        _write_target(tmp_path, "def boom(): raise ValueError('oops')")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::boom",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success  # snapshot still written
        content = result.snapshot_files[0].read_text()
        assert "EXCEPTION" in content
        assert "oops" in content


# ---------------------------------------------------------------------------
# Verification (diff) phase tests
# ---------------------------------------------------------------------------


class TestVerifyAgainstSnapshots:
    def test_passes_when_output_unchanged(self, tmp_path):
        _write_target(tmp_path, "def greet(name): return f'hello {name}'")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::greet",
                    "sample_inputs": [["world"]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert isinstance(result, VerificationResult)
        assert result.passed is True
        assert result.diffs == []

    def test_fails_when_output_changes(self, tmp_path):
        _write_target(tmp_path, "def greet(name): return f'hello {name}'")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::greet",
                    "sample_inputs": [["world"]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        # Mutate the implementation
        _write_target(tmp_path, "def greet(name): return f'goodbye {name}'")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert len(result.diffs) > 0
        assert "goodbye" in result.diffs[0] or "hello" in result.diffs[0]

    def test_fails_when_snapshot_dir_missing(self, tmp_path):
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "nonexistent/snapshots/",
                }
            }
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert "does not exist" in result.details

    def test_fails_when_snapshot_file_missing_for_input(self, tmp_path):
        _write_target(tmp_path, "def f(x): return x")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::f",
                    "sample_inputs": [[1]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        # snapshot_dir exists but no snapshot file
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_allow_changes_suppresses_matching_diffs(self, tmp_path):
        _write_target(tmp_path, "def f(): return 'result: 2024-01-01'")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                    "allow_changes": ["*result*"],
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        _write_target(tmp_path, "def f(): return 'result: 2025-06-10'")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True

    def test_allow_changes_does_not_suppress_unmatched_diffs(self, tmp_path):
        _write_target(tmp_path, "def f(): return 'hello'")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                    "allow_changes": ["*timestamp*"],
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        _write_target(tmp_path, "def f(): return 'goodbye'")
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False

    def test_bad_target_returns_failure(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "missing_mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is False
        assert "Target resolution failed" in result.details

    def test_details_message_on_pass(self, tmp_path):
        _write_target(tmp_path, "def f(): return 1")
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "target_mod.py::f",
                    "sample_inputs": "auto",
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        observe_and_snapshot(ac, tmp_path)
        result = verify_against_snapshots(ac, tmp_path)
        assert result.passed is True
        assert "match" in result.details.lower() or "baseline" in result.details.lower()


# ---------------------------------------------------------------------------
# Integration: bob3.acceptance is importable
# ---------------------------------------------------------------------------


class TestBob3AcceptanceIntegration:
    def test_package_is_importable(self):
        import bob3.acceptance  # noqa: F401

    def test_characterization_ac_accessible_from_package(self):
        from bob3.acceptance import CharacterizationAC
        assert CharacterizationAC is not None

    def test_parse_characterization_ac_accessible_from_package(self):
        from bob3.acceptance import parse_characterization_ac
        assert callable(parse_characterization_ac)

    def test_kinds_module_importable(self):
        from bob3.acceptance import kinds  # noqa: F401

    def test_kinds_module_importable_direct(self):
        from bob3.acceptance.kinds import (
            CharacterizationAC,
            SnapshotResult,
            VerificationResult,
            observe_and_snapshot,
            parse_characterization_ac,
            verify_against_snapshots,
        )
        assert all(
            x is not None
            for x in [
                CharacterizationAC,
                SnapshotResult,
                VerificationResult,
                observe_and_snapshot,
                parse_characterization_ac,
                verify_against_snapshots,
            ]
        )
