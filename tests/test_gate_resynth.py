"""Tests for bob.gate_resynth — gate-blocked feature re-synthesis.

Verifies the one-attempt-per-feature livelock prevention, correct delegation to
the score-gate synthesizer, and correct return values.
"""
from __future__ import annotations

import pytest
import asyncio


# ---------------------------------------------------------------------------
# Import verification
# ---------------------------------------------------------------------------

def test_module_importable():
    import bob.gate_resynth as gr
    assert hasattr(gr, "resynthesize_gate_blocked_feature")
    assert hasattr(gr, "is_synthesis_attempted")
    assert callable(gr.resynthesize_gate_blocked_feature)
    assert callable(gr.is_synthesis_attempted)


def test_orchestrator_exposes_resynthesize():
    from bob.orchestrator import resynthesize_gate_blocked_feature
    assert callable(resynthesize_gate_blocked_feature)


def test_score_gate_exposes_score_gate_loop():
    from bob.score_gate import score_gate_loop
    assert callable(score_gate_loop)


# ---------------------------------------------------------------------------
# Validation / error-path tests
# ---------------------------------------------------------------------------

def test_raises_on_none_feature_id():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gr.resynthesize_gate_blocked_feature(
            feature_id=None,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_raises_on_empty_feature_id():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gr.resynthesize_gate_blocked_feature(
            feature_id="",
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_raises_on_int_feature_id():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gr.resynthesize_gate_blocked_feature(
            feature_id=42,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_raises_on_none_project_id():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gr.resynthesize_gate_blocked_feature(
            feature_id="feat-1",
            name="Feature",
            description="Desc",
            project_id=None,  # type: ignore[arg-type]
        )


def test_raises_on_empty_project_id():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        gr.resynthesize_gate_blocked_feature(
            feature_id="feat-1",
            name="Feature",
            description="Desc",
            project_id="",
        )


# ---------------------------------------------------------------------------
# Livelock prevention: already-attempted returns (None, 0.0)
# ---------------------------------------------------------------------------

def test_already_attempted_returns_null_tuple():
    """Second call for same feature_id must return (None, 0.0) — livelock guard."""
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    gr._synthesis_attempted.add("feat-dup")
    result = gr.resynthesize_gate_blocked_feature(
        feature_id="feat-dup",
        name="Some Feature",
        description="Some description",
        project_id="proj-dup",
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] is None
    assert result[1] == 0.0


def test_is_synthesis_attempted_after_call():
    """After a successful call the feature_id must be in the attempted set."""
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()

    # Provide a synthesizer that fails gracefully — we don't want real LLM calls.
    async def _fake_score_gate_fn(**kwargs):
        return None

    gr.resynthesize_gate_blocked_feature(
        feature_id="feat-track",
        name="Feature",
        description="Desc",
        project_id="proj-track",
        score_gate_fn=_fake_score_gate_fn,
        synthesize_fn=lambda **kw: None,
    )
    assert gr.is_synthesis_attempted("feat-track")


# ---------------------------------------------------------------------------
# Delegate path: successful re-synthesis returns (criteria, composite)
# ---------------------------------------------------------------------------

def test_successful_synthesis_returns_criteria():
    """When the synthesizer produces criteria the function returns them."""
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()

    class _FakeReport:
        criteria = ["AC1: must do X", "AC2: must not do Y"]
        composite = 0.92
        gate_passed = True

    async def _fake_score_gate_fn(**kwargs):
        return _FakeReport()

    result = gr.resynthesize_gate_blocked_feature(
        feature_id="feat-ok",
        name="Feature OK",
        description="Desc",
        project_id="proj-ok",
        score_gate_fn=_fake_score_gate_fn,
        synthesize_fn=lambda **kw: None,
    )
    assert isinstance(result, tuple)
    new_acs, composite = result
    assert new_acs == ["AC1: must do X", "AC2: must not do Y"]
    assert abs(composite - 0.92) < 1e-9


def test_synthesis_failure_returns_null_tuple():
    """When the synthesizer raises, the function returns (None, 0.0) gracefully."""
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()

    async def _broken_score_gate_fn(**kwargs):
        raise RuntimeError("LLM timeout")

    result = gr.resynthesize_gate_blocked_feature(
        feature_id="feat-fail",
        name="Feature",
        description="Desc",
        project_id="proj-fail",
        score_gate_fn=_broken_score_gate_fn,
        synthesize_fn=lambda **kw: None,
    )
    assert result == (None, 0.0)


def test_synthesis_none_report_returns_null_tuple():
    """When score_gate_fn returns None the function returns (None, 0.0)."""
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()

    async def _none_score_gate_fn(**kwargs):
        return None

    result = gr.resynthesize_gate_blocked_feature(
        feature_id="feat-none",
        name="Feature",
        description="Desc",
        project_id="proj-none",
        score_gate_fn=_none_score_gate_fn,
        synthesize_fn=lambda **kw: None,
    )
    assert result == (None, 0.0)


# ---------------------------------------------------------------------------
# is_synthesis_attempted predicate edge cases
# ---------------------------------------------------------------------------

def test_is_synthesis_attempted_false_for_unknown():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    assert gr.is_synthesis_attempted("never-seen") is False


def test_is_synthesis_attempted_false_for_empty():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    assert gr.is_synthesis_attempted("") is False


def test_is_synthesis_attempted_false_for_none():
    import bob.gate_resynth as gr
    gr._synthesis_attempted.clear()
    assert gr.is_synthesis_attempted(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: bob.score_gate module
# ---------------------------------------------------------------------------

def test_score_gate_module_exposes_callable():
    import bob.score_gate as sg
    assert callable(sg.score_gate_loop)
