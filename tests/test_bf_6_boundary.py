"""Boundary-case tests for BF-6 — Characterization AC kind.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising unexpected exceptions.

Boundary cases tested:
  - ac_spec=None  → graceful dict result, no crash
  - ac_spec={}    → graceful dict result, no crash
  - ac_spec=""    → graceful dict result, no crash
  - sample_inputs with (0,) → snapshot written without crash
  - sample_inputs=[] (empty list) → no snapshots, success=True (no inputs to fail)
  - Bar().method(0) → returns 'result=0' (zero boundary, no ValueError)
  - sample_inputs() returns list that includes (0,) zero boundary
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.bf_6_characterization_ac_kind_approval_test_diffs_legacy import (
    bf_6_characterization_ac_kind_approval_test_diffs_legacy as dispatch,
    sample_inputs,
)
from bob.acceptance.kinds import (
    CharacterizationAC,
    observe_and_snapshot,
    parse_characterization_ac,
)
from foo.bar import Bar, bar_method


class TestBoundaryNoneEmptyInput:
    def test_none_ac_spec_returns_dict_not_raises(self):
        result = dispatch(None)
        assert isinstance(result, dict)
        assert "passed" in result

    def test_none_ac_spec_passed_is_false(self):
        result = dispatch(None)
        assert result["passed"] is False

    def test_empty_dict_ac_spec_returns_dict_not_raises(self):
        result = dispatch({})
        assert isinstance(result, dict)
        assert result["passed"] is False

    def test_empty_string_ac_spec_returns_dict_not_raises(self):
        result = dispatch("")
        assert isinstance(result, dict)
        assert result["passed"] is False

    def test_result_has_required_keys(self):
        result = dispatch(None)
        assert set(result.keys()) >= {"passed", "detail", "diffs", "phase"}


class TestBoundaryZeroInput:
    def test_bar_method_zero_returns_result_zero(self):
        bar = Bar()
        output = bar.method(0)
        assert output == "result=0"

    def test_bar_method_zero_does_not_raise(self):
        bar = Bar()
        # Zero is the boundary value — must not raise ValueError
        result = bar.method(0)
        assert isinstance(result, str)

    def test_bar_method_one_returns_result_two(self):
        bar = Bar()
        assert bar.method(1) == "result=2"

    def test_bar_function_zero_does_not_raise(self):
        assert bar_method(0) == "result=0"


class TestBoundarySampleInputs:
    def test_sample_inputs_returns_list(self):
        inputs = sample_inputs()
        assert isinstance(inputs, list)

    def test_sample_inputs_non_empty(self):
        inputs = sample_inputs()
        assert len(inputs) > 0

    def test_sample_inputs_includes_zero_boundary(self):
        inputs = sample_inputs()
        assert (0,) in inputs

    def test_sample_inputs_contains_tuples(self):
        inputs = sample_inputs()
        for item in inputs:
            assert isinstance(item, tuple)


class TestBoundaryObserverPhaseZeroInput:
    def test_observe_snapshot_with_zero_input(self, tmp_path):
        target_file = tmp_path / "mod.py"
        target_file.write_text(
            textwrap.dedent("def double(x): return x * 2\n"),
            encoding="utf-8",
        )
        ac = parse_characterization_ac(
            {
                "characterization": {
                    "target": "mod.py::double",
                    "sample_inputs": [[0]],
                    "snapshot_dir": "snapshots/",
                }
            }
        )
        result = observe_and_snapshot(ac, tmp_path)
        assert result.success is True
        assert len(result.snapshot_files) == 1
        content = result.snapshot_files[0].read_text()
        assert "0" in content

    def test_observe_with_empty_sample_inputs_list(self, tmp_path):
        target_file = tmp_path / "mod.py"
        target_file.write_text(
            textwrap.dedent("def f(x): return x\n"),
            encoding="utf-8",
        )
        ac = CharacterizationAC(
            target="mod.py::f",
            sample_inputs=[],
            snapshot_dir="snapshots/",
        )
        result = observe_and_snapshot(ac, tmp_path)
        # Empty inputs list → no calls, no snapshots, no errors
        assert result.success is True
        assert result.snapshot_files == []
        assert result.errors == []
