"""Tests for bob.gate_blocked_resynth (feature 077582eb).

Covers the AC-named entry points:
- resynthesize_gate_blocked_feature: one bounded AC re-synthesis per feature.
- has_resynthesized: whether a feature has already been attempted.
"""
import importlib

import pytest

import bob.gate_blocked_resynth as gbr
import bob73.gate_blocker as gb


@pytest.fixture(autouse=True)
def _clear_state():
    gb._synthesis_attempted.clear()
    yield
    gb._synthesis_attempted.clear()


def test_module_and_symbols_exist():
    mod = importlib.import_module("bob.gate_blocked_resynth")
    assert hasattr(mod, "resynthesize_gate_blocked_feature")
    assert hasattr(mod, "has_resynthesized")
    assert callable(mod.resynthesize_gate_blocked_feature)
    assert callable(mod.has_resynthesized)


def test_has_resynthesized_false_before_attempt():
    assert gbr.has_resynthesized("feat-1") is False


def test_has_resynthesized_true_after_attempt():
    gb.mark_synthesis_attempted("feat-1")
    assert gbr.has_resynthesized("feat-1") is True


def test_has_resynthesized_rejects_none():
    with pytest.raises(ValueError):
        gbr.has_resynthesized(None)  # type: ignore[arg-type]


def test_has_resynthesized_rejects_empty():
    with pytest.raises(ValueError):
        gbr.has_resynthesized("")


def test_has_resynthesized_rejects_int():
    with pytest.raises(ValueError):
        gbr.has_resynthesized(42)  # type: ignore[arg-type]


def test_resynthesize_marks_attempted():
    """A successful synthesizer call marks the feature as attempted."""
    def fake_synth(*args, **kwargs):
        return None

    async def fake_gate(**kwargs):
        class Report:
            criteria = ["AC one", "AC two"]
            composite = 0.9
        return Report()

    acs, composite = gbr.resynthesize_gate_blocked_feature(
        feature_id="feat-ok",
        name="Feature",
        description="Desc",
        project_id="proj",
        synthesize_fn=fake_synth,
        score_gate_fn=fake_gate,
    )
    assert acs == ["AC one", "AC two"]
    assert composite == pytest.approx(0.9)
    assert gbr.has_resynthesized("feat-ok") is True


def test_resynthesize_bounded_to_one_attempt():
    """Second call for the same feature returns (None, 0.0) without re-running."""
    calls = {"n": 0}

    async def fake_gate(**kwargs):
        calls["n"] += 1
        class Report:
            criteria = ["AC"]
            composite = 0.88
        return Report()

    first = gbr.resynthesize_gate_blocked_feature(
        feature_id="feat-once",
        name="F",
        description="D",
        project_id="p",
        synthesize_fn=lambda *a, **k: None,
        score_gate_fn=fake_gate,
    )
    assert first[0] == ["AC"]

    second = gbr.resynthesize_gate_blocked_feature(
        feature_id="feat-once",
        name="F",
        description="D",
        project_id="p",
        synthesize_fn=lambda *a, **k: None,
        score_gate_fn=fake_gate,
    )
    assert second == (None, 0.0)
    assert calls["n"] == 1  # synthesizer ran exactly once — no livelock


def test_resynthesize_returns_none_when_no_criteria():
    """When synthesis yields no criteria, returns (None, 0.0) but stays attempted."""
    async def fake_gate(**kwargs):
        class Report:
            criteria = []
            composite = 0.0
        return Report()

    acs, composite = gbr.resynthesize_gate_blocked_feature(
        feature_id="feat-empty",
        name="F",
        description="D",
        project_id="p",
        synthesize_fn=lambda *a, **k: None,
        score_gate_fn=fake_gate,
    )
    assert acs is None
    assert composite == 0.0
    assert gbr.has_resynthesized("feat-empty") is True


def test_resynthesize_rejects_none_feature_id():
    with pytest.raises(ValueError):
        gbr.resynthesize_gate_blocked_feature(
            feature_id=None,  # type: ignore[arg-type]
            name="F",
            description="D",
            project_id="p",
        )


def test_resynthesize_rejects_empty_feature_id():
    with pytest.raises(ValueError):
        gbr.resynthesize_gate_blocked_feature(
            feature_id="",
            name="F",
            description="D",
            project_id="p",
        )


def test_resynthesize_rejects_none_project_id():
    with pytest.raises(ValueError):
        gbr.resynthesize_gate_blocked_feature(
            feature_id="feat-x",
            name="F",
            description="D",
            project_id=None,  # type: ignore[arg-type]
        )


def test_shared_state_with_underlying_module():
    """has_resynthesized reflects the shared bob73.gate_blocker set."""
    assert gbr.has_resynthesized("shared-feat") is False
    gbr.mark_synthesis_attempted("shared-feat")
    assert "shared-feat" in gb._synthesis_attempted
    assert gbr.has_resynthesized("shared-feat") is True
