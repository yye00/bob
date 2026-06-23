"""Tests for bob3.gate_blocked_synthesizer (feature adb882e4).

Verifies that gate-blocked features are re-synthesized exactly once per process
(no livelock), that invalid input raises ValueError, and that the function
returns the expected tuple type.
"""

from __future__ import annotations

import importlib
import pytest


# ---------------------------------------------------------------------------
# Reset module state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_resynthesis_state():
    """Reset the module-level idempotency set before each test."""
    import bob3.gate_blocked_synthesizer as mod
    mod._resynthesis_attempted.clear()
    yield
    mod._resynthesis_attempted.clear()


# ---------------------------------------------------------------------------
# Module / attribute surface
# ---------------------------------------------------------------------------

def test_module_importable():
    mod = importlib.import_module("bob3.gate_blocked_synthesizer")
    assert mod is not None


def test_re_synthesize_blocked_feature_defined():
    mod = importlib.import_module("bob3.gate_blocked_synthesizer")
    assert hasattr(mod, "re_synthesize_blocked_feature")
    assert callable(mod.re_synthesize_blocked_feature)


def test_is_resynthesis_attempted_defined():
    mod = importlib.import_module("bob3.gate_blocked_synthesizer")
    assert hasattr(mod, "is_resynthesis_attempted")
    assert callable(mod.is_resynthesis_attempted)


# ---------------------------------------------------------------------------
# is_resynthesis_attempted predicate
# ---------------------------------------------------------------------------

def test_is_resynthesis_attempted_false_initially():
    import bob3.gate_blocked_synthesizer as mod
    assert mod.is_resynthesis_attempted("feat-new") is False


def test_is_resynthesis_attempted_true_after_mark():
    import bob3.gate_blocked_synthesizer as mod
    mod._resynthesis_attempted.add("feat-marked")
    assert mod.is_resynthesis_attempted("feat-marked") is True


def test_is_resynthesis_attempted_false_for_empty():
    import bob3.gate_blocked_synthesizer as mod
    assert mod.is_resynthesis_attempted("") is False


def test_is_resynthesis_attempted_false_for_non_str():
    import bob3.gate_blocked_synthesizer as mod
    assert mod.is_resynthesis_attempted(None) is False  # type: ignore[arg-type]
    assert mod.is_resynthesis_attempted(42) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Input validation (ValueError on bad input)
# ---------------------------------------------------------------------------

def test_raises_value_error_on_none_feature_id():
    import bob3.gate_blocked_synthesizer as mod
    with pytest.raises(ValueError):
        mod.re_synthesize_blocked_feature(
            feature_id=None,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_raises_value_error_on_empty_feature_id():
    import bob3.gate_blocked_synthesizer as mod
    with pytest.raises(ValueError):
        mod.re_synthesize_blocked_feature(
            feature_id="",
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_raises_value_error_on_int_feature_id():
    import bob3.gate_blocked_synthesizer as mod
    with pytest.raises(ValueError, match="str"):
        mod.re_synthesize_blocked_feature(
            feature_id=42,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_raises_value_error_on_none_project_id():
    import bob3.gate_blocked_synthesizer as mod
    with pytest.raises(ValueError):
        mod.re_synthesize_blocked_feature(
            feature_id="feat-valid",
            name="Feature",
            description="Desc",
            project_id=None,  # type: ignore[arg-type]
        )


def test_raises_value_error_on_empty_project_id():
    import bob3.gate_blocked_synthesizer as mod
    with pytest.raises(ValueError):
        mod.re_synthesize_blocked_feature(
            feature_id="feat-valid",
            name="Feature",
            description="Desc",
            project_id="",
        )


# ---------------------------------------------------------------------------
# Idempotency: bounded to ONE re-synthesis per feature per process
# ---------------------------------------------------------------------------

def test_returns_none_when_already_attempted():
    """Second call for the same feature returns (None, 0.0) without calling synthesizer."""
    import bob3.gate_blocked_synthesizer as mod

    calls = []

    async def fake_score_gate_fn(**kwargs):
        calls.append(kwargs)
        return None

    mod._resynthesis_attempted.add("feat-already")
    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-already",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=fake_score_gate_fn,
    )
    assert result == (None, 0.0)
    assert len(calls) == 0, "Synthesizer must not be called when already attempted"


def test_marks_feature_as_attempted_on_first_call():
    """First call marks the feature in _resynthesis_attempted."""
    import bob3.gate_blocked_synthesizer as mod

    async def fake_score_gate_fn(**kwargs):
        return None

    assert "feat-first" not in mod._resynthesis_attempted
    mod.re_synthesize_blocked_feature(
        feature_id="feat-first",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=fake_score_gate_fn,
    )
    assert "feat-first" in mod._resynthesis_attempted


def test_second_call_returns_none_without_synthesizer():
    """Second call for same feature_id returns (None, 0.0) — livelock prevention."""
    import bob3.gate_blocked_synthesizer as mod

    async def fake_gate_pass(**kwargs):
        class R:
            criteria = ["File exists: src/foo.py"]
            composite = 0.9
        return R()

    # First call
    mod.re_synthesize_blocked_feature(
        feature_id="feat-second",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=fake_gate_pass,
    )
    # Second call — must return (None, 0.0)
    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-second",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=fake_gate_pass,
    )
    assert result == (None, 0.0)


# ---------------------------------------------------------------------------
# Happy path: re-synthesis succeeds and returns (criteria, composite)
# ---------------------------------------------------------------------------

def test_returns_criteria_on_success():
    """When synthesizer returns valid criteria, result is (criteria_list, composite)."""
    import bob3.gate_blocked_synthesizer as mod

    expected_criteria = ["File exists: src/foo.py", "Function defined: foo.bar"]
    expected_composite = 0.92

    async def fake_score_gate_fn(**kwargs):
        class Report:
            criteria = expected_criteria
            composite = expected_composite
        return Report()

    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-happy",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=fake_score_gate_fn,
    )
    assert result[0] == expected_criteria
    assert abs(result[1] - expected_composite) < 1e-9


def test_returns_none_when_synthesizer_returns_no_criteria():
    """When synthesizer returns a report with no criteria, returns (None, 0.0)."""
    import bob3.gate_blocked_synthesizer as mod

    async def fake_score_gate_fn(**kwargs):
        class Report:
            criteria = []
            composite = 0.0
        return Report()

    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-empty-criteria",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=fake_score_gate_fn,
    )
    assert result == (None, 0.0)


def test_returns_none_when_synthesizer_raises():
    """When synthesizer raises, returns (None, 0.0) without propagating."""
    import bob3.gate_blocked_synthesizer as mod

    async def failing_gate(**kwargs):
        raise RuntimeError("LLM unavailable")

    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-fail",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=failing_gate,
    )
    assert result == (None, 0.0)
    # Feature must still be marked as attempted so we don't loop
    assert "feat-fail" in mod._resynthesis_attempted


def test_returns_none_when_synthesizer_returns_none():
    """When synthesizer returns None (gate didn't pass), returns (None, 0.0)."""
    import bob3.gate_blocked_synthesizer as mod

    async def none_gate(**kwargs):
        return None

    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-none-report",
        name="Feature",
        description="Desc",
        project_id="proj-1",
        score_gate_fn=none_gate,
    )
    assert result == (None, 0.0)


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

def test_return_type_is_tuple_of_two():
    """re_synthesize_blocked_feature always returns a 2-tuple."""
    import bob3.gate_blocked_synthesizer as mod

    async def fake(**kwargs):
        return None

    result = mod.re_synthesize_blocked_feature(
        feature_id="feat-type",
        name="n",
        description="d",
        project_id="p",
        score_gate_fn=fake,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
