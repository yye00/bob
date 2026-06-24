"""Tests asserting handle_unknown_failure_class returns empty list on FailureClass.unknown (zero/empty boundary)."""

import pytest
from bob.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    handle_unknown_failure_class,
    research_strategies,
    never_spawns_research_on_unknown,
)


def test_handle_unknown_returns_empty_list():
    result = handle_unknown_failure_class(FailureClass.unknown)
    assert result == []


def test_handle_unknown_returns_list_type():
    result = handle_unknown_failure_class(FailureClass.unknown)
    assert isinstance(result, list)


def test_handle_unknown_returns_zero_strategies():
    result = handle_unknown_failure_class(FailureClass.unknown)
    assert len(result) == 0


def test_research_strategies_returns_empty_for_unknown():
    result = research_strategies(FailureClass.unknown)
    assert result == []


def test_never_spawns_research_on_unknown_returns_true():
    assert never_spawns_research_on_unknown() is True


def test_research_strategies_non_empty_for_all_classifiable():
    """All non-unknown failure classes return at least one strategy."""
    classifiable = [fc for fc in FailureClass if fc != FailureClass.unknown]
    for fc in classifiable:
        strategies = research_strategies(fc)
        assert len(strategies) >= 1, (
            f"research_strategies({fc!r}) returned empty list; expected at least 1 strategy"
        )


def test_handle_unknown_does_not_raise():
    """handle_unknown_failure_class must not raise for FailureClass.unknown."""
    try:
        result = handle_unknown_failure_class(FailureClass.unknown)
    except Exception as e:
        pytest.fail(f"handle_unknown_failure_class raised unexpectedly: {e}")


def test_all_strategies_from_unknown_are_strategy_instances():
    """Even if something is returned (it shouldn't be), it must be Strategy instances."""
    result = handle_unknown_failure_class(FailureClass.unknown)
    for item in result:
        assert isinstance(item, Strategy)
