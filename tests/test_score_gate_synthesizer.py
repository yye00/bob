"""Tests for bob.score_gate_synthesizer (feature d987030c).

Verifies that the score_gate_synthesizer module correctly exposes
score_gate_loop and synthesize_for_feature as the canonical entry points
for gate-blocked feature re-synthesis.
"""
from __future__ import annotations

import importlib
import inspect

import pytest


def test_module_importable():
    mod = importlib.import_module("bob.score_gate_synthesizer")
    assert mod is not None


def test_score_gate_loop_exported():
    mod = importlib.import_module("bob.score_gate_synthesizer")
    assert hasattr(mod, "score_gate_loop"), "score_gate_loop must be exported"
    assert callable(mod.score_gate_loop)


def test_synthesize_for_feature_exported():
    mod = importlib.import_module("bob.score_gate_synthesizer")
    assert hasattr(mod, "synthesize_for_feature"), "synthesize_for_feature must be exported"
    assert callable(mod.synthesize_for_feature)


def test_score_gate_report_exported():
    mod = importlib.import_module("bob.score_gate_synthesizer")
    assert hasattr(mod, "ScoreGateReport"), "ScoreGateReport must be exported"


def test_score_gate_loop_is_coroutine():
    from bob.score_gate_synthesizer import score_gate_loop
    assert inspect.iscoroutinefunction(score_gate_loop), (
        "score_gate_loop must be an async function"
    )


def test_synthesize_for_feature_is_coroutine():
    from bob.score_gate_synthesizer import synthesize_for_feature
    assert inspect.iscoroutinefunction(synthesize_for_feature), (
        "synthesize_for_feature must be an async function"
    )


def test_score_gate_loop_same_as_spec_synthesizer():
    """The re-exported score_gate_loop must be the same callable as spec_synthesizer's."""
    from bob.score_gate_synthesizer import score_gate_loop as sgs_fn
    from bob.spec_synthesizer import score_gate_loop as ss_fn
    assert sgs_fn is ss_fn


def test_synthesize_for_feature_same_as_spec_synthesizer():
    """The re-exported synthesize_for_feature must be the same callable as spec_synthesizer's."""
    from bob.score_gate_synthesizer import synthesize_for_feature as sgs_fn
    from bob.spec_synthesizer import synthesize_for_feature as ss_fn
    assert sgs_fn is ss_fn


def test_score_gate_loop_rejects_missing_required_args():
    """score_gate_loop called with no args raises TypeError (required keyword args)."""
    import asyncio
    from bob.score_gate_synthesizer import score_gate_loop

    with pytest.raises(TypeError):
        asyncio.get_event_loop().run_until_complete(score_gate_loop())


def test_score_gate_loop_accepts_injectable_synthesize_fn():
    """score_gate_loop can be called with a custom synthesize_fn that returns criteria."""
    import asyncio
    from bob.score_gate_synthesizer import score_gate_loop

    async def stub_synthesize(**kwargs):
        return ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

    loop = asyncio.new_event_loop()
    try:
        report = loop.run_until_complete(
            score_gate_loop(
                synthesize_fn=stub_synthesize,
                title="Test Feature",
                description="A test feature",
                project_id="proj-test",
                max_retries=1,
            )
        )
    finally:
        loop.close()

    assert report is not None
    assert hasattr(report, "gate_passed")
    assert hasattr(report, "criteria")
    assert hasattr(report, "composite")


def test_all_exports_in_all():
    mod = importlib.import_module("bob.score_gate_synthesizer")
    assert hasattr(mod, "__all__")
    assert "score_gate_loop" in mod.__all__
    assert "synthesize_for_feature" in mod.__all__
