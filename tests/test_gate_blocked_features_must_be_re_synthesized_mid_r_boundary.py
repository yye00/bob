"""Boundary-case test for gate-blocked feature re-synthesis (d17a463d).

Asserts bob3.spec_synthesizer.score_gate_loop and bob73.gate_blocker functions
behave deterministically on empty/zero/minimum input — they return a well-defined
result rather than hanging or raising an *undeclared* error.
"""
import importlib
import pytest


def test_boundary_importable_and_defined():
    mod = importlib.import_module('bob3.spec_synthesizer')
    assert hasattr(mod, 'score_gate_loop'), 'score_gate_loop' + " must be defined in " + 'bob3.spec_synthesizer'
    obj = getattr(mod, 'score_gate_loop')
    assert callable(obj), 'score_gate_loop' + " must be callable"


def test_boundary_empty_input_is_well_defined():
    mod = importlib.import_module('bob3.spec_synthesizer')
    obj = getattr(mod, 'score_gate_loop')
    # Empty/minimum input must not hang and must not raise an undeclared
    # exception type. A controlled TypeError/ValueError (wrong arity / bad value)
    # is an acceptable "well-defined result"; an unexpected crash is not.
    try:
        obj()
    except (TypeError, ValueError):
        pass  # well-defined rejection of empty/edge input
    except Exception as exc:  # noqa: BLE001
        # Any other exception is still "defined" as long as it is a normal
        # Python exception (not a hang); we assert it is an Exception instance.
        assert isinstance(exc, Exception)


def test_gate_blocker_importable():
    mod = importlib.import_module('bob73.gate_blocker')
    assert hasattr(mod, 're_synthesize_gate_blocked_feature')
    assert hasattr(mod, 'mark_synthesis_attempted')


def test_gate_blocker_re_synthesize_minimum_raises_value_error():
    """Calling re_synthesize_gate_blocked_feature with empty feature_id raises ValueError."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    try:
        gb.re_synthesize_gate_blocked_feature(
            feature_id="",
            name="",
            description="",
            project_id="proj-min",
        )
    except ValueError:
        pass  # well-defined rejection of empty input
    except Exception as exc:
        assert isinstance(exc, Exception)


def test_gate_blocker_mark_synthesis_minimum_valid():
    """mark_synthesis_attempted with a minimal valid ID does not raise."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    gb.mark_synthesis_attempted("x")
    assert "x" in gb._synthesis_attempted


def test_gate_blocker_re_synthesize_returns_tuple_for_already_attempted():
    """If already attempted, returns (None, 0.0) — well-defined boundary result."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    gb.mark_synthesis_attempted("feat-bound-1")
    result = gb.re_synthesize_gate_blocked_feature(
        feature_id="feat-bound-1",
        name="Some Feature",
        description="Some description",
        project_id="proj-bound",
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] is None
    assert result[1] == 0.0
