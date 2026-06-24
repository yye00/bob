"""Tests for bob3.gate_blocked_feature_recovery (feature 36b33b52).

Covers the three public functions:
  - synthesize_blocked_feature_ac — one-shot AC re-synthesis for gate-blocked features
  - mark_re_synthesized — idempotency sentinel
  - is_gate_blocked — gate predicate
"""

from __future__ import annotations

import importlib
import pytest
import bob3.gate_blocked_feature_recovery as recovery


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


def test_module_importable():
    mod = importlib.import_module("bob3.gate_blocked_feature_recovery")
    assert mod is not None


def test_synthesize_blocked_feature_ac_defined():
    assert hasattr(recovery, "synthesize_blocked_feature_ac")
    assert callable(recovery.synthesize_blocked_feature_ac)


def test_mark_re_synthesized_defined():
    assert hasattr(recovery, "mark_re_synthesized")
    assert callable(recovery.mark_re_synthesized)


def test_is_gate_blocked_defined():
    assert hasattr(recovery, "is_gate_blocked")
    assert callable(recovery.is_gate_blocked)


# ---------------------------------------------------------------------------
# is_gate_blocked
# ---------------------------------------------------------------------------


def test_is_gate_blocked_below_threshold():
    assert recovery.is_gate_blocked(0.80) is True


def test_is_gate_blocked_at_threshold():
    assert recovery.is_gate_blocked(0.85) is False


def test_is_gate_blocked_above_threshold():
    assert recovery.is_gate_blocked(0.90) is False


def test_is_gate_blocked_zero():
    assert recovery.is_gate_blocked(0.0) is True


def test_is_gate_blocked_one():
    assert recovery.is_gate_blocked(1.0) is False


def test_is_gate_blocked_custom_threshold():
    assert recovery.is_gate_blocked(0.70, threshold=0.75) is True
    assert recovery.is_gate_blocked(0.80, threshold=0.75) is False


def test_is_gate_blocked_invalid_score_raises():
    with pytest.raises(ValueError):
        recovery.is_gate_blocked("not-a-number")  # type: ignore[arg-type]


def test_is_gate_blocked_invalid_threshold_raises():
    with pytest.raises(ValueError):
        recovery.is_gate_blocked(0.5, threshold="high")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# mark_re_synthesized
# ---------------------------------------------------------------------------


def test_mark_re_synthesized_adds_to_set():
    recovery._re_synthesized.discard("test-mark-001")
    recovery.mark_re_synthesized("test-mark-001")
    assert "test-mark-001" in recovery._re_synthesized
    recovery._re_synthesized.discard("test-mark-001")


def test_mark_re_synthesized_idempotent():
    recovery._re_synthesized.discard("test-mark-002")
    recovery.mark_re_synthesized("test-mark-002")
    recovery.mark_re_synthesized("test-mark-002")  # second call must not raise
    assert "test-mark-002" in recovery._re_synthesized
    recovery._re_synthesized.discard("test-mark-002")


def test_mark_re_synthesized_empty_raises():
    with pytest.raises(ValueError):
        recovery.mark_re_synthesized("")


def test_mark_re_synthesized_none_raises():
    with pytest.raises(ValueError):
        recovery.mark_re_synthesized(None)  # type: ignore[arg-type]


def test_mark_re_synthesized_non_str_raises():
    with pytest.raises(ValueError):
        recovery.mark_re_synthesized(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# synthesize_blocked_feature_ac — idempotency (already attempted)
# ---------------------------------------------------------------------------


def test_synthesize_already_attempted_returns_none_tuple():
    fid = "already-attempted-feat-1"
    recovery._re_synthesized.discard(fid)
    recovery.mark_re_synthesized(fid)
    result = recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="Some Feature",
        description="Some description",
        project_id="proj-1",
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] is None
    assert result[1] == 0.0
    recovery._re_synthesized.discard(fid)


# ---------------------------------------------------------------------------
# synthesize_blocked_feature_ac — invalid inputs raise ValueError
# ---------------------------------------------------------------------------


def test_synthesize_none_feature_id_raises():
    with pytest.raises(ValueError):
        recovery.synthesize_blocked_feature_ac(
            feature_id=None,  # type: ignore[arg-type]
            name="F",
            description="D",
            project_id="proj-x",
        )


def test_synthesize_empty_feature_id_raises():
    with pytest.raises(ValueError):
        recovery.synthesize_blocked_feature_ac(
            feature_id="",
            name="F",
            description="D",
            project_id="proj-x",
        )


def test_synthesize_int_feature_id_raises():
    with pytest.raises(ValueError, match="str"):
        recovery.synthesize_blocked_feature_ac(
            feature_id=99,  # type: ignore[arg-type]
            name="F",
            description="D",
            project_id="proj-x",
        )


def test_synthesize_none_project_id_raises():
    with pytest.raises(ValueError):
        recovery.synthesize_blocked_feature_ac(
            feature_id="feat-err-pi",
            name="F",
            description="D",
            project_id=None,  # type: ignore[arg-type]
        )


def test_synthesize_empty_project_id_raises():
    with pytest.raises(ValueError):
        recovery.synthesize_blocked_feature_ac(
            feature_id="feat-err-pi2",
            name="F",
            description="D",
            project_id="",
        )


# ---------------------------------------------------------------------------
# synthesize_blocked_feature_ac — successful stub synthesizer
# ---------------------------------------------------------------------------


_UNSET = object()


def _make_stub_report(criteria=_UNSET, composite=0.9):
    class _Report:
        pass

    r = _Report()
    r.criteria = ["AC1", "AC2"] if criteria is _UNSET else criteria
    r.composite = composite
    r.gate_passed = composite >= 0.85
    return r


async def _stub_synthesize_fn(**kwargs):
    return _make_stub_report()


async def _stub_score_gate_fn(synthesize_fn, title, description, project_id, **kwargs):
    return _make_stub_report()


def test_synthesize_calls_score_gate_fn_and_returns_criteria():
    fid = "feat-stub-synth-001"
    recovery._re_synthesized.discard(fid)

    result = recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="My Feature",
        description="My description",
        project_id="proj-stub",
        synthesize_fn=_stub_synthesize_fn,
        score_gate_fn=_stub_score_gate_fn,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    acs, composite = result
    assert isinstance(acs, list)
    assert len(acs) >= 1
    assert isinstance(composite, float)
    assert composite > 0.0
    recovery._re_synthesized.discard(fid)


def test_synthesize_marks_feature_as_attempted():
    fid = "feat-marks-attempted-001"
    recovery._re_synthesized.discard(fid)

    recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="F",
        description="D",
        project_id="proj-mark",
        synthesize_fn=_stub_synthesize_fn,
        score_gate_fn=_stub_score_gate_fn,
    )
    assert fid in recovery._re_synthesized
    recovery._re_synthesized.discard(fid)


def test_synthesize_second_call_is_idempotent():
    fid = "feat-idempotent-001"
    recovery._re_synthesized.discard(fid)

    first = recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="F",
        description="D",
        project_id="proj-idem",
        synthesize_fn=_stub_synthesize_fn,
        score_gate_fn=_stub_score_gate_fn,
    )
    second = recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="F",
        description="D",
        project_id="proj-idem",
        synthesize_fn=_stub_synthesize_fn,
        score_gate_fn=_stub_score_gate_fn,
    )
    assert first[0] is not None  # first call synthesized
    assert second[0] is None  # second call skipped (idempotent)
    assert second[1] == 0.0
    recovery._re_synthesized.discard(fid)


def test_synthesize_returns_none_when_score_gate_fails():
    fid = "feat-failed-001"
    recovery._re_synthesized.discard(fid)

    async def _failing_gate(**kwargs):
        raise RuntimeError("synthesizer LLM error")

    result = recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="F",
        description="D",
        project_id="proj-fail",
        synthesize_fn=_stub_synthesize_fn,
        score_gate_fn=_failing_gate,
    )
    assert result == (None, 0.0)
    recovery._re_synthesized.discard(fid)


def test_synthesize_returns_none_when_report_has_no_criteria():
    fid = "feat-no-criteria-001"
    recovery._re_synthesized.discard(fid)

    async def _empty_report_gate(**kwargs):
        return _make_stub_report(criteria=None)

    # When report.criteria is None the function should return (None, 0.0)
    # (the module checks `if report and report.criteria`)
    result = recovery.synthesize_blocked_feature_ac(
        feature_id=fid,
        name="F",
        description="D",
        project_id="proj-empty",
        synthesize_fn=_stub_synthesize_fn,
        score_gate_fn=_empty_report_gate,
    )
    assert result == (None, 0.0)
    recovery._re_synthesized.discard(fid)
