"""Tests for orchestrator gate-blocking integration (feature d987030c).

Verifies that bob.orchestrator exposes promote_gate_blocked_features and that
the gate-blocked re-synthesis path correctly prevents livelock by bounding
re-synthesis to exactly one attempt per feature per process.
"""
from __future__ import annotations

import importlib

import pytest


def test_orchestrator_exports_promote_gate_blocked_features():
    """bob.orchestrator must expose promote_gate_blocked_features."""
    mod = importlib.import_module("bob.orchestrator")
    assert hasattr(mod, "promote_gate_blocked_features"), (
        "bob.orchestrator must export promote_gate_blocked_features"
    )
    assert callable(mod.promote_gate_blocked_features)


def test_promote_gate_blocked_features_raises_on_invalid_feature_id():
    """promote_gate_blocked_features raises ValueError for non-string feature_id."""
    from bob.orchestrator import promote_gate_blocked_features
    import bob.gate_resynth as gr

    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        promote_gate_blocked_features(
            feature_id=None,  # type: ignore[arg-type]
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_promote_gate_blocked_features_raises_on_empty_feature_id():
    """promote_gate_blocked_features raises ValueError for empty feature_id."""
    from bob.orchestrator import promote_gate_blocked_features
    import bob.gate_resynth as gr

    gr._synthesis_attempted.clear()
    with pytest.raises(ValueError):
        promote_gate_blocked_features(
            feature_id="",
            name="Feature",
            description="Desc",
            project_id="proj-1",
        )


def test_promote_gate_blocked_features_idempotent_after_first_attempt():
    """Second call for the same feature returns (None, 0.0) — no livelock."""
    import bob.gate_resynth as gr
    from bob.orchestrator import promote_gate_blocked_features

    gr._synthesis_attempted.clear()

    called = []

    async def fake_score_gate_fn(**kwargs):
        called.append(kwargs)

        class FakeReport:
            criteria = ["File exists: src/foo.py"]
            composite = 0.9
            gate_passed = True

        return FakeReport()

    async def fake_synthesize(**kwargs):
        return ["File exists: src/foo.py"]

    # First call: runs the synthesizer
    result1 = promote_gate_blocked_features(
        feature_id="feat-idempotent-1",
        name="Feature",
        description="Desc",
        project_id="proj-idem",
        synthesize_fn=fake_synthesize,
        score_gate_fn=fake_score_gate_fn,
    )
    # First call records the attempt
    assert gr.is_synthesis_attempted("feat-idempotent-1") is True

    # Second call: immediately returns (None, 0.0) without re-running synthesizer
    called_before = len(called)
    result2 = promote_gate_blocked_features(
        feature_id="feat-idempotent-1",
        name="Feature",
        description="Desc",
        project_id="proj-idem",
        synthesize_fn=fake_synthesize,
        score_gate_fn=fake_score_gate_fn,
    )
    assert result2 == (None, 0.0), "Second call must return (None, 0.0) — no livelock"
    assert len(called) == called_before, "Synthesizer must NOT be called on second attempt"


def test_promote_gate_blocked_features_returns_tuple():
    """promote_gate_blocked_features always returns a 2-tuple."""
    import bob.gate_resynth as gr
    from bob.orchestrator import promote_gate_blocked_features

    gr._synthesis_attempted.clear()

    async def fake_score_gate_fn(**kwargs):
        class FakeReport:
            criteria = ["pytest: tests/test_foo.py", "File exists: src/foo.py"]
            composite = 0.88
            gate_passed = True

        return FakeReport()

    async def fake_synthesize(**kwargs):
        return ["pytest: tests/test_foo.py", "File exists: src/foo.py"]

    result = promote_gate_blocked_features(
        feature_id="feat-tuple-check",
        name="Test Feature",
        description="A test feature for the tuple return check",
        project_id="proj-tuple",
        synthesize_fn=fake_synthesize,
        score_gate_fn=fake_score_gate_fn,
    )

    assert isinstance(result, tuple), "promote_gate_blocked_features must return a tuple"
    assert len(result) == 2, "Tuple must have exactly 2 elements"


def test_promote_gate_blocked_features_records_attempt():
    """After calling promote_gate_blocked_features, the feature is marked as attempted."""
    import bob.gate_resynth as gr
    from bob.orchestrator import promote_gate_blocked_features, is_already_resynthesized

    gr._synthesis_attempted.clear()

    async def fake_score_gate_fn(**kwargs):
        class FakeReport:
            criteria = None
            composite = 0.3
            gate_passed = False

        return FakeReport()

    async def fake_synthesize(**kwargs):
        return None

    feature_id = "feat-record-attempt"
    assert not is_already_resynthesized(feature_id)

    promote_gate_blocked_features(
        feature_id=feature_id,
        name="Feature",
        description="Desc",
        project_id="proj-rec",
        synthesize_fn=fake_synthesize,
        score_gate_fn=fake_score_gate_fn,
    )

    assert is_already_resynthesized(feature_id), (
        "Feature must be marked as attempted after promote_gate_blocked_features call"
    )


def test_is_already_resynthesized_exported():
    """bob.orchestrator must also expose is_already_resynthesized."""
    mod = importlib.import_module("bob.orchestrator")
    assert hasattr(mod, "is_already_resynthesized"), (
        "bob.orchestrator must export is_already_resynthesized"
    )
    assert callable(mod.is_already_resynthesized)


def test_orchestrator_integration_imports():
    """All gate-blocking related names must be importable from bob.orchestrator."""
    mod = importlib.import_module("bob.orchestrator")
    for name in ("promote_gate_blocked_features", "is_already_resynthesized",
                 "resynthesize_gate_blocked_features"):
        assert hasattr(mod, name), f"bob.orchestrator must export {name!r}"
