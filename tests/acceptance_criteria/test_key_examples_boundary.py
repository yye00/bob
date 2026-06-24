"""Boundary tests for KeyExampleAC in bob.acceptance_criteria.key_examples."""

from __future__ import annotations

import pytest

from bob.acceptance_criteria.key_examples import KeyExampleAC
from bob.spec_quality.example_grammar import KeyExample


class TestKeyExampleACBoundaryInputs:
    def test_empty_entries_list_returns_no_examples(self):
        ac = KeyExampleAC.from_entries([])
        assert ac.examples == []

    def test_none_entries_list_returns_no_examples(self):
        ac = KeyExampleAC.from_entries(None)
        assert ac.examples == []

    def test_all_none_entries_skipped(self):
        ac = KeyExampleAC.from_entries([None, None])
        assert ac.examples == []

    def test_zero_given_value_accepted(self):
        ac = KeyExampleAC.from_entries([{"given": "0", "then": "0"}])
        assert len(ac.examples) == 1
        assert ac.examples[0].given == "0"

    def test_empty_string_given_value_accepted(self):
        ac = KeyExampleAC.from_entries([{"given": "", "then": "expected"}])
        assert len(ac.examples) == 1
        assert ac.examples[0].given == ""

    def test_single_example_parametrize_test_not_empty(self):
        ac = KeyExampleAC.from_entries([{"given": "0", "then": "0"}])
        code = ac.parametrize_test(seed=0)
        assert "@pytest.mark.parametrize" in code

    def test_empty_examples_parametrize_test_is_empty(self):
        ac = KeyExampleAC.from_entries([])
        assert ac.parametrize_test() == ""

    def test_boundary_not_required_for_non_numeric_ac(self):
        ac = KeyExampleAC.from_entries([], behavior_ac="system logs authentication event")
        assert ac.boundary_required is False
        assert ac.boundary_satisfied is True

    def test_boundary_required_for_numeric_ac(self):
        ac = KeyExampleAC.from_entries(
            [],
            behavior_ac="system converts integer value to string",
        )
        assert ac.boundary_required is True

    def test_boundary_satisfied_with_zero_example(self):
        ac = KeyExampleAC.from_entries(
            [{"given": "0", "then": "0"}],
            behavior_ac="system converts integer value to string",
        )
        assert ac.boundary_satisfied is True

    def test_boundary_not_satisfied_without_boundary_example(self):
        ac = KeyExampleAC.from_entries(
            [{"given": "5", "then": "25"}],
            behavior_ac="system converts integer value to string",
        )
        assert ac.boundary_satisfied is False

    def test_few_shot_snippet_empty_when_no_examples(self):
        ac = KeyExampleAC.from_entries([])
        assert ac.few_shot_snippet == ""

    def test_few_shot_snippet_lists_examples(self):
        ac = KeyExampleAC.from_entries([{"given": "x=1", "then": "y=1"}])
        snippet = ac.few_shot_snippet
        assert "key_examples:" in snippet
        assert "x=1" in snippet
