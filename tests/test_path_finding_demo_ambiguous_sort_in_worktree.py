"""Tests demonstrating path-finding retry with ambiguous sort AC in worktree context."""

import pathlib

import pytest
import yaml

from bob3.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    classify_failure,
    research_strategies,
    should_trigger,
    inject_into_implementer_prompt,
)


SPEC_PATH = pathlib.Path(__file__).parent.parent / "bob4" / "research" / "demonstrators" / "F-R7-474" / "spec.yaml"


def _load_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text())


def test_spec_file_exists_for_worktree_demo():
    assert SPEC_PATH.exists(), f"F-R7-474 demonstrator spec must exist at {SPEC_PATH}"


def test_ambiguous_sort_spec_triggers_ambiguous_ac_class():
    """The ambiguous sort spec's failure class is ambiguous_ac."""
    failure_info = {"failure_class": "ambiguous_ac", "message": "sort somehow — unclear criterion"}
    result = classify_failure(failure_info)
    assert result == FailureClass.ambiguous_ac


def test_path_finding_triggers_at_attempt_two_for_ambiguous_sort():
    failure_info = {"failure_class": "ambiguous_ac"}
    assert should_trigger(2, failure_info) is True


def test_path_finding_does_not_trigger_at_attempt_one_for_ambiguous_sort():
    failure_info = {"failure_class": "ambiguous_ac"}
    assert should_trigger(1, failure_info) is False


def test_ambiguous_sort_research_strategies_returned():
    strategies = research_strategies(FailureClass.ambiguous_ac)
    assert len(strategies) >= 1
    for s in strategies:
        assert isinstance(s, Strategy)
        assert s.failure_class == FailureClass.ambiguous_ac


def test_ambiguous_sort_strategy_titles_are_non_empty():
    strategies = research_strategies(FailureClass.ambiguous_ac)
    for s in strategies:
        assert s.title.strip(), "Strategy title must be non-empty"
        assert s.description.strip(), "Strategy description must be non-empty"


def test_inject_strategies_into_ambiguous_sort_prompt():
    base_prompt = "Implement the sort function as described in the spec."
    strategies = research_strategies(FailureClass.ambiguous_ac)
    enhanced = inject_into_implementer_prompt(base_prompt, strategies, FailureClass.ambiguous_ac, attempt_number=2)

    assert base_prompt in enhanced
    assert "ambiguous_ac" in enhanced.lower() or "ambiguous" in enhanced.lower()
    assert "Research-Augmented Retry" in enhanced


def test_inject_with_no_strategies_returns_base_prompt():
    base_prompt = "Some base prompt."
    enhanced = inject_into_implementer_prompt(base_prompt, [], FailureClass.unknown, attempt_number=2)
    assert enhanced == base_prompt


def test_spec_ambiguity_markers_exist():
    spec = _load_spec()
    markers = spec.get("ambiguity_markers", [])
    assert len(markers) >= 1, "F-R7-474 spec must declare ambiguity_markers for the demo"
