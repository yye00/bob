"""Tests for bob3.orchestrator.gate_resynthesis (feature 066763fc).

Verifies that gate-blocked features are re-synthesized exactly once per
process, that the idempotency boundary is enforced (no livelock), and
that invalid inputs are rejected with ValueError.
"""

from __future__ import annotations

import pytest

import bob3.orchestrator.gate_resynthesis as gr


def _clear():
    gr._resynthesis_attempted.clear()


# ---------------------------------------------------------------------------
# mark_resynthesis_attempted
# ---------------------------------------------------------------------------


class TestMarkResynthesisAttempted:
    def setup_method(self):
        _clear()

    def test_marks_feature_id(self):
        gr.mark_resynthesis_attempted("feat-abc")
        assert "feat-abc" in gr._resynthesis_attempted

    def test_marks_multiple_ids(self):
        gr.mark_resynthesis_attempted("feat-1")
        gr.mark_resynthesis_attempted("feat-2")
        assert "feat-1" in gr._resynthesis_attempted
        assert "feat-2" in gr._resynthesis_attempted

    def test_idempotent_double_mark(self):
        gr.mark_resynthesis_attempted("feat-x")
        gr.mark_resynthesis_attempted("feat-x")
        assert "feat-x" in gr._resynthesis_attempted

    def test_raises_on_none(self):
        with pytest.raises(ValueError):
            gr.mark_resynthesis_attempted(None)  # type: ignore[arg-type]

    def test_raises_on_empty(self):
        with pytest.raises(ValueError):
            gr.mark_resynthesis_attempted("")

    def test_raises_on_int(self):
        with pytest.raises(ValueError, match="str"):
            gr.mark_resynthesis_attempted(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resynthesized_ac_for_blocked_feature — validation
# ---------------------------------------------------------------------------


class TestResynthesizedAcValidation:
    def setup_method(self):
        _clear()

    def test_raises_on_none_feature_id(self):
        with pytest.raises(ValueError):
            gr.resynthesized_ac_for_blocked_feature(
                feature_id=None,  # type: ignore[arg-type]
                name="F",
                description="D",
                project_id="proj",
            )

    def test_raises_on_empty_feature_id(self):
        with pytest.raises(ValueError):
            gr.resynthesized_ac_for_blocked_feature(
                feature_id="",
                name="F",
                description="D",
                project_id="proj",
            )

    def test_raises_on_int_feature_id(self):
        with pytest.raises(ValueError, match="str"):
            gr.resynthesized_ac_for_blocked_feature(
                feature_id=123,  # type: ignore[arg-type]
                name="F",
                description="D",
                project_id="proj",
            )

    def test_raises_on_none_project_id(self):
        with pytest.raises(ValueError):
            gr.resynthesized_ac_for_blocked_feature(
                feature_id="feat-val-1",
                name="F",
                description="D",
                project_id=None,  # type: ignore[arg-type]
            )

    def test_raises_on_empty_project_id(self):
        with pytest.raises(ValueError):
            gr.resynthesized_ac_for_blocked_feature(
                feature_id="feat-val-2",
                name="F",
                description="D",
                project_id="",
            )


# ---------------------------------------------------------------------------
# resynthesized_ac_for_blocked_feature — idempotency (livelock prevention)
# ---------------------------------------------------------------------------


class TestResynthesizedAcIdempotency:
    def setup_method(self):
        _clear()

    def test_second_call_returns_none_tuple(self):
        gr.mark_resynthesis_attempted("feat-idem-1")
        result = gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-idem-1",
            name="F",
            description="D",
            project_id="proj",
        )
        assert result == (None, 0.0)

    def test_second_call_does_not_invoke_synthesizer(self):
        calls = []

        async def fake_score_gate(**kwargs):
            calls.append(kwargs)
            return None

        gr.mark_resynthesis_attempted("feat-idem-2")
        gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-idem-2",
            name="F",
            description="D",
            project_id="proj",
            synthesize_fn=lambda **kw: None,
            score_gate_fn=fake_score_gate,
        )
        assert calls == [], "synthesizer must NOT be called for already-attempted feature"

    def test_marks_as_attempted_on_first_call(self):
        """First call must mark the feature so subsequent calls skip."""

        async def fake_score_gate(**kwargs):
            return None  # simulate no criteria returned

        gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-idem-3",
            name="F",
            description="D",
            project_id="proj",
            synthesize_fn=lambda **kw: None,
            score_gate_fn=fake_score_gate,
        )
        assert "feat-idem-3" in gr._resynthesis_attempted


# ---------------------------------------------------------------------------
# resynthesized_ac_for_blocked_feature — happy path via injected synthesizer
# ---------------------------------------------------------------------------


class TestResynthesizedAcHappyPath:
    def setup_method(self):
        _clear()

    def test_returns_criteria_on_success(self):
        new_acs = ["AC1: do X", "AC2: do Y"]

        class FakeReport:
            criteria = new_acs
            composite = 0.91

        async def fake_score_gate(**kwargs):
            return FakeReport()

        acs, score = gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-happy-1",
            name="My Feature",
            description="Does stuff",
            project_id="proj-happy",
            synthesize_fn=lambda **kw: None,
            score_gate_fn=fake_score_gate,
        )
        assert acs == new_acs
        assert score == pytest.approx(0.91)

    def test_returns_none_tuple_when_report_has_no_criteria(self):
        class FakeReport:
            criteria = []
            composite = 0.5

        async def fake_score_gate(**kwargs):
            return FakeReport()

        result = gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-happy-2",
            name="F",
            description="D",
            project_id="proj",
            synthesize_fn=lambda **kw: None,
            score_gate_fn=fake_score_gate,
        )
        assert result == (None, 0.0)

    def test_returns_none_tuple_when_report_is_none(self):
        async def fake_score_gate(**kwargs):
            return None

        result = gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-happy-3",
            name="F",
            description="D",
            project_id="proj",
            synthesize_fn=lambda **kw: None,
            score_gate_fn=fake_score_gate,
        )
        assert result == (None, 0.0)

    def test_returns_none_tuple_on_synthesizer_exception(self):
        async def fake_score_gate(**kwargs):
            raise RuntimeError("LLM timeout")

        result = gr.resynthesized_ac_for_blocked_feature(
            feature_id="feat-happy-4",
            name="F",
            description="D",
            project_id="proj",
            synthesize_fn=lambda **kw: None,
            score_gate_fn=fake_score_gate,
        )
        assert result == (None, 0.0)


# ---------------------------------------------------------------------------
# Integration: module importable and __all__ correct
# ---------------------------------------------------------------------------


def test_module_importable():
    import importlib
    mod = importlib.import_module("bob3.orchestrator.gate_resynthesis")
    assert hasattr(mod, "resynthesized_ac_for_blocked_feature")
    assert hasattr(mod, "mark_resynthesis_attempted")
    assert callable(mod.resynthesized_ac_for_blocked_feature)
    assert callable(mod.mark_resynthesis_attempted)


def test_all_exports():
    import bob3.orchestrator.gate_resynthesis as mod
    assert "resynthesized_ac_for_blocked_feature" in mod.__all__
    assert "mark_resynthesis_attempted" in mod.__all__
