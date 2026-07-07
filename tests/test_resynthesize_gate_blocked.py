"""Tests for gate-blocked feature mid-run re-synthesis (87fb9f99).

Root cause of the "scoring never increases" livelock: a feature that fails the
spec_quality gate (composite < 0.85) stays 'pending'; the run loop's only
recovery was to re-dispatch to test-writer/CodeT, which rebuild CODE — but the
score depends on the ACCEPTANCE CRITERIA, not the code, so it never rises.

Fix under test: ``bob.orchestrator.resynthesize_gate_blocked_feature`` re-runs
the score-gate synthesizer on a blocked feature to regenerate its ACs, bounded
to exactly ONE attempt per feature per process so a still-blocked feature is
left pending without re-spinning (no livelock).
"""
import types

import pytest

import bob.gate_blocked_synthesizer as gbs
from bob.orchestrator import resynthesize_gate_blocked_feature


@pytest.fixture(autouse=True)
def _clear_attempted():
    gbs._resynthesis_attempted.clear()
    yield
    gbs._resynthesis_attempted.clear()


def _fake_report(criteria, composite):
    return types.SimpleNamespace(criteria=criteria, composite=composite)


def _make_score_gate_fn(criteria, composite):
    async def _fn(*, synthesize_fn, title, description, project_id, workspace=None):
        return _fake_report(criteria, composite)
    return _fn


def test_exported_from_orchestrator_and_callable():
    assert callable(resynthesize_gate_blocked_feature)


def test_resynthesis_returns_new_acs_and_composite():
    new_acs = ["Function defined: x.y", "pytest: tests/test_x.py"]
    fn = _make_score_gate_fn(new_acs, 0.91)
    acs, composite = resynthesize_gate_blocked_feature(
        feature_id="feat-1",
        name="Feature One",
        description="desc",
        project_id="proj",
        score_gate_fn=fn,
        synthesize_fn=lambda *a, **k: None,
    )
    assert acs == new_acs
    assert composite == pytest.approx(0.91)


def test_bounded_to_one_attempt_per_feature():
    """Second call for the same feature returns (None, 0.0) — no re-spin."""
    fn = _make_score_gate_fn(["ac"], 0.9)
    first = resynthesize_gate_blocked_feature(
        feature_id="feat-dup",
        name="n",
        description="d",
        project_id="proj",
        score_gate_fn=fn,
        synthesize_fn=lambda *a, **k: None,
    )
    assert first[0] == ["ac"]

    calls = []

    async def _tracking(*, synthesize_fn, title, description, project_id, workspace=None):
        calls.append(feature_marker)
        return _fake_report(["ac2"], 0.99)

    feature_marker = object()
    second = resynthesize_gate_blocked_feature(
        feature_id="feat-dup",
        name="n",
        description="d",
        project_id="proj",
        score_gate_fn=_tracking,
        synthesize_fn=lambda *a, **k: None,
    )
    assert second == (None, 0.0)
    assert calls == [], "synthesizer must not run twice for same feature (livelock guard)"


def test_still_blocked_after_resynth_is_left_without_respin():
    """A feature that stays < 0.85 after one re-synth is not retried."""
    fn = _make_score_gate_fn(["weak-ac"], 0.40)
    acs, composite = resynthesize_gate_blocked_feature(
        feature_id="feat-weak",
        name="n",
        description="d",
        project_id="proj",
        score_gate_fn=fn,
        synthesize_fn=lambda *a, **k: None,
    )
    # criteria were produced but composite is still below the gate
    assert acs == ["weak-ac"]
    assert composite == pytest.approx(0.40)
    # marked attempted -> further calls are no-ops
    assert gbs.is_resynthesis_attempted("feat-weak") is True
    again = resynthesize_gate_blocked_feature(
        feature_id="feat-weak",
        name="n",
        description="d",
        project_id="proj",
        score_gate_fn=fn,
        synthesize_fn=lambda *a, **k: None,
    )
    assert again == (None, 0.0)


def test_synth_exception_returns_none_and_marks_attempted():
    """If synthesis raises, return (None, 0.0) and still consume the attempt."""
    async def _boom(*, synthesize_fn, title, description, project_id, workspace=None):
        raise RuntimeError("synth failed")

    acs, composite = resynthesize_gate_blocked_feature(
        feature_id="feat-boom",
        name="n",
        description="d",
        project_id="proj",
        score_gate_fn=_boom,
        synthesize_fn=lambda *a, **k: None,
    )
    assert acs is None
    assert composite == 0.0
    assert gbs.is_resynthesis_attempted("feat-boom") is True


def test_empty_criteria_report_returns_none():
    fn = _make_score_gate_fn([], 0.0)
    acs, composite = resynthesize_gate_blocked_feature(
        feature_id="feat-empty",
        name="n",
        description="d",
        project_id="proj",
        score_gate_fn=fn,
        synthesize_fn=lambda *a, **k: None,
    )
    assert acs is None
    assert composite == 0.0


def test_raises_valueerror_on_bad_feature_id():
    with pytest.raises(ValueError):
        resynthesize_gate_blocked_feature(
            feature_id="",
            name="n",
            description="d",
            project_id="proj",
        )
    with pytest.raises(ValueError, match="str"):
        resynthesize_gate_blocked_feature(
            feature_id=123,  # type: ignore[arg-type]
            name="n",
            description="d",
            project_id="proj",
        )


def test_raises_valueerror_on_bad_project_id():
    with pytest.raises(ValueError):
        resynthesize_gate_blocked_feature(
            feature_id="feat-x",
            name="n",
            description="d",
            project_id="",
        )


def test_is_resynthesis_attempted_false_for_unknown():
    assert gbs.is_resynthesis_attempted("never-seen") is False
    assert gbs.is_resynthesis_attempted("") is False
