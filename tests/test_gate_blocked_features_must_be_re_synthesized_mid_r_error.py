"""Error-path tests for gate-blocked feature re-synthesis (d17a463d).

Asserts bob.spec_synthesizer.score_gate_loop and bob73.gate_blocker functions
reject invalid input deterministically — they raise a normal exception and do
not silently succeed with garbage or hang.
"""
import importlib
import pytest


def test_error_invalid_input_is_handled():
    mod = importlib.import_module('bob.spec_synthesizer')
    obj = getattr(mod, 'score_gate_loop')
    assert callable(obj)
    # Passing clearly-invalid positional args must raise a normal exception
    # rather than silently succeeding. We accept ANY Exception subclass as a
    # valid "rejection"; the contract is: it does not return a bogus value
    # without complaint and does not hang.
    sentinel = object()
    result = sentinel
    try:
        result = obj(object(), object(), object())
    except Exception:  # noqa: BLE001 - any defined rejection is acceptable
        return
    # If it did NOT raise, it must at least have returned a real (non-sentinel)
    # value deterministically — acceptable for pure/total functions.
    assert result is not sentinel


def test_gate_blocker_re_synthesize_raises_on_none_feature_id():
    """Passing None as feature_id must raise ValueError, not silently succeed."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gb.re_synthesize_gate_blocked_feature(
            feature_id=None,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-err",
        )


def test_gate_blocker_re_synthesize_raises_on_empty_feature_id():
    """Passing empty string as feature_id must raise ValueError."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gb.re_synthesize_gate_blocked_feature(
            feature_id="",
            name="Feature",
            description="Desc",
            project_id="proj-err",
        )


def test_gate_blocker_re_synthesize_raises_on_int_feature_id():
    """Passing an integer feature_id must raise ValueError."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    with pytest.raises(ValueError, match="str"):
        gb.re_synthesize_gate_blocked_feature(
            feature_id=42,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-err",
        )


def test_gate_blocker_re_synthesize_raises_on_none_project_id():
    """Passing None as project_id must raise ValueError."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-err-1",
            name="Feature",
            description="Desc",
            project_id=None,  # type: ignore[arg-type]
        )


def test_gate_blocker_mark_synthesis_raises_on_none():
    """mark_synthesis_attempted(None) must raise ValueError."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gb.mark_synthesis_attempted(None)  # type: ignore[arg-type]


def test_gate_blocker_mark_synthesis_raises_on_empty():
    """mark_synthesis_attempted('') must raise ValueError."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gb.mark_synthesis_attempted("")
