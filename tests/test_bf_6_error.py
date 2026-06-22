"""Error-path tests for BF-6 — Characterization AC kind.

Verifies that invalid inputs raise ValueError and that the function does
not silently succeed (i.e., no false-positive 'passed=True' on bad input).

Error cases tested:
  - Bar().method(negative) → raises ValueError
  - dispatch with invalid phase → raises ValueError
  - dispatch with non-characterization non-empty string → raises ValueError
  - dispatch with dict missing 'characterization' key → raises ValueError
  - parse_characterization_ac dict with empty target → returns None (rejected)
"""

from __future__ import annotations

import pytest

from bob3.bf_6_characterization_ac_kind_approval_test_diffs_legacy import (
    bf_6_characterization_ac_kind_approval_test_diffs_legacy as dispatch,
)
from bob3.acceptance.kinds import parse_characterization_ac
from foo.bar import Bar, bar_method


class TestBarMethodErrorPaths:
    def test_negative_value_raises_value_error(self):
        bar = Bar()
        with pytest.raises(ValueError, match="non-negative"):
            bar.method(-1)

    def test_negative_value_does_not_return_silently(self):
        bar = Bar()
        raised = False
        try:
            bar.method(-5)
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for negative input, but none was raised"

    def test_bar_function_negative_raises(self):
        with pytest.raises(ValueError):
            bar_method(-1)


class TestDispatchErrorPaths:
    def test_invalid_phase_raises_value_error(self):
        with pytest.raises(ValueError, match="phase"):
            dispatch(
                {
                    "characterization": {
                        "target": "src/foo/bar.py::bar_method",
                        "sample_inputs": [[1]],
                        "snapshot_dir": "tests/snapshots/err/",
                    }
                },
                phase="invalid_phase",
            )

    def test_invalid_phase_does_not_silently_succeed(self):
        raised = False
        try:
            result = dispatch(
                {"characterization": {"target": "t", "sample_inputs": "auto", "snapshot_dir": "s/"}},
                phase="bad",
            )
            # If no exception raised, the result must not be passed=True
            assert result.get("passed") is not True, "Expected failure but got passed=True"
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for bad phase, but none was raised"

    def test_non_characterization_string_raises_value_error(self):
        with pytest.raises(ValueError):
            dispatch("pytest: tests/test_foo.py")

    def test_dict_without_characterization_key_raises_value_error(self):
        with pytest.raises(ValueError):
            dispatch({"behavior": "something happens"})

    def test_error_result_passed_is_false(self):
        result = dispatch(None)
        assert result["passed"] is False

    def test_error_result_has_detail_message(self):
        result = dispatch(None)
        assert isinstance(result["detail"], str)
        assert len(result["detail"]) > 0


class TestParseErrorPaths:
    def test_parse_returns_none_for_empty_characterization_body_target(self):
        # dict form with no 'target' key → returns None (rejected cleanly)
        result = parse_characterization_ac({"characterization": {"snapshot_dir": "s/"}})
        assert result is None

    def test_parse_returns_none_for_non_dict_body(self):
        result = parse_characterization_ac({"characterization": 123})
        assert result is None

    def test_parse_returns_none_for_irrelevant_string(self):
        result = parse_characterization_ac("File exists: src/foo.py")
        assert result is None

    def test_parse_returns_none_for_none_input(self):
        result = parse_characterization_ac(None)
        assert result is None

    def test_parse_returns_none_for_integer_input(self):
        result = parse_characterization_ac(42)
        assert result is None
