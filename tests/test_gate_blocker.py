"""Tests for bob73.gate_blocker — gate-blocked feature re-synthesis.

Covers:
- re_synthesize_gate_blocked_feature: happy path, already-attempted guard,
  synthesis failure handling, bad-input validation.
- mark_synthesis_attempted: marks correctly, idempotent.
- Integration shape: result tuple structure, once-per-process bound.
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeReport:
    criteria: list[str] | None
    composite: float
    gate_passed: bool = True
    gate_failed: bool = False
    gate_avg_attempts: int = 1


def _make_fake_score_gate(criteria: list[str] | None, composite: float):
    """Return an async callable that mimics score_gate_loop's interface."""
    async def _fake(*, synthesize_fn, title, description, project_id, workspace=None):
        return _FakeReport(criteria=criteria, composite=composite)
    return _fake


def _make_fake_synthesize():
    async def _fake(*, project_id, title, description, **kwargs):
        return ["AC1: does something", "AC2: does another thing"]
    return _fake


# ---------------------------------------------------------------------------
# Helpers to reset module state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_attempted_set():
    """Clear the module-level _synthesis_attempted set before each test."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()
    yield
    gb._synthesis_attempted.clear()


# ---------------------------------------------------------------------------
# Tests: mark_synthesis_attempted
# ---------------------------------------------------------------------------

class TestMarkSynthesisAttempted:
    def test_marks_feature(self):
        import bob73.gate_blocker as gb
        gb.mark_synthesis_attempted("feat-123")
        assert "feat-123" in gb._synthesis_attempted

    def test_idempotent(self):
        import bob73.gate_blocker as gb
        gb.mark_synthesis_attempted("feat-abc")
        gb.mark_synthesis_attempted("feat-abc")
        assert gb._synthesis_attempted.count if hasattr(gb._synthesis_attempted, "count") else True
        assert "feat-abc" in gb._synthesis_attempted

    def test_raises_on_non_string(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError, match="str"):
            gb.mark_synthesis_attempted(123)  # type: ignore[arg-type]

    def test_raises_on_empty_string(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError, match="non-empty"):
            gb.mark_synthesis_attempted("")

    def test_raises_on_none(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError):
            gb.mark_synthesis_attempted(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: re_synthesize_gate_blocked_feature
# ---------------------------------------------------------------------------

class TestReSynthesizeGateBlockedFeature:
    def test_returns_criteria_and_score_on_success(self):
        import bob73.gate_blocker as gb
        acs = ["pytest: tests/foo.py", "Function defined: bar.baz"]
        gate_fn = _make_fake_score_gate(acs, 0.92)
        synth_fn = _make_fake_synthesize()

        result, score = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-001",
            name="Some Feature",
            description="Does something useful",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert result == acs
        assert abs(score - 0.92) < 1e-6

    def test_returns_none_if_already_attempted(self):
        import bob73.gate_blocker as gb
        acs = ["pytest: tests/foo.py"]
        gate_fn = _make_fake_score_gate(acs, 0.90)
        synth_fn = _make_fake_synthesize()

        # First call: should synthesize
        r1, s1 = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-002",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert r1 is not None

        # Second call with same feature_id: should skip
        r2, s2 = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-002",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert r2 is None
        assert s2 == 0.0

    def test_marks_as_attempted_before_synthesizing(self):
        """Feature ID must be in _synthesis_attempted even if synthesis fails."""
        import bob73.gate_blocker as gb

        async def _failing_gate(**kwargs):
            raise RuntimeError("synthesizer exploded")

        r, s = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-003",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            score_gate_fn=_failing_gate,
            synthesize_fn=_make_fake_synthesize(),
        )
        # Should return gracefully
        assert r is None
        assert s == 0.0
        # Feature must be marked as attempted even after failure
        assert "feat-003" in gb._synthesis_attempted

    def test_returns_none_when_report_has_no_criteria(self):
        import bob73.gate_blocker as gb
        gate_fn = _make_fake_score_gate(None, 0.0)
        synth_fn = _make_fake_synthesize()

        r, s = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-004",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert r is None
        assert s == 0.0

    def test_returns_none_when_report_is_none(self):
        import bob73.gate_blocker as gb

        async def _none_gate(**kwargs):
            return None

        r, s = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-005",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            score_gate_fn=_none_gate,
            synthesize_fn=_make_fake_synthesize(),
        )
        assert r is None
        assert s == 0.0

    def test_raises_on_non_string_feature_id(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError, match="str"):
            gb.re_synthesize_gate_blocked_feature(
                feature_id=42,  # type: ignore[arg-type]
                name="Feature",
                description="Desc",
                project_id="proj-1",
            )

    def test_raises_on_empty_feature_id(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError, match="non-empty"):
            gb.re_synthesize_gate_blocked_feature(
                feature_id="",
                name="Feature",
                description="Desc",
                project_id="proj-1",
            )

    def test_raises_on_empty_project_id(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError, match="non-empty"):
            gb.re_synthesize_gate_blocked_feature(
                feature_id="feat-006",
                name="Feature",
                description="Desc",
                project_id="",
            )

    def test_raises_on_non_string_project_id(self):
        import bob73.gate_blocker as gb
        with pytest.raises(ValueError, match="str"):
            gb.re_synthesize_gate_blocked_feature(
                feature_id="feat-007",
                name="Feature",
                description="Desc",
                project_id=None,  # type: ignore[arg-type]
            )

    def test_independent_features_get_independent_attempts(self):
        """Two different feature IDs each get one synthesis attempt."""
        import bob73.gate_blocker as gb
        acs = ["pytest: tests/foo.py"]
        gate_fn = _make_fake_score_gate(acs, 0.88)
        synth_fn = _make_fake_synthesize()

        r1, _ = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-A",
            name="Feature A",
            description="Desc A",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        r2, _ = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-B",
            name="Feature B",
            description="Desc B",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert r1 is not None
        assert r2 is not None

    def test_workspace_path_forwarded(self):
        """workspace parameter must be forwarded to the gate function."""
        import bob73.gate_blocker as gb

        captured: dict = {}

        async def _capture_gate(*, synthesize_fn, title, description, project_id, workspace=None):
            captured["workspace"] = workspace
            return _FakeReport(criteria=["AC: something"], composite=0.9)

        ws = Path("/tmp/workspace_test")
        gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-008",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            workspace=ws,
            score_gate_fn=_capture_gate,
            synthesize_fn=_make_fake_synthesize(),
        )
        assert captured.get("workspace") == ws


# ---------------------------------------------------------------------------
# Tests: module-level imports / integration shape
# ---------------------------------------------------------------------------

class TestModuleIntegration:
    def test_importable(self):
        mod = importlib.import_module("bob73.gate_blocker")
        assert mod is not None

    def test_re_synthesize_gate_blocked_feature_defined(self):
        mod = importlib.import_module("bob73.gate_blocker")
        assert hasattr(mod, "re_synthesize_gate_blocked_feature")
        assert callable(mod.re_synthesize_gate_blocked_feature)

    def test_mark_synthesis_attempted_defined(self):
        mod = importlib.import_module("bob73.gate_blocker")
        assert hasattr(mod, "mark_synthesis_attempted")
        assert callable(mod.mark_synthesis_attempted)

    def test_result_is_tuple_of_two(self):
        import bob73.gate_blocker as gb
        gate_fn = _make_fake_score_gate(["AC1"], 0.87)
        synth_fn = _make_fake_synthesize()
        result = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-tuple",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_score_is_float(self):
        import bob73.gate_blocker as gb
        gate_fn = _make_fake_score_gate(["AC1"], 0.87)
        synth_fn = _make_fake_synthesize()
        _, score = gb.re_synthesize_gate_blocked_feature(
            feature_id="feat-float",
            name="Feature",
            description="Desc",
            project_id="proj-1",
            synthesize_fn=synth_fn,
            score_gate_fn=gate_fn,
        )
        assert isinstance(score, float)
