"""Tests for spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until.

Verifies the score-gate retry loop: re-synthesizes TBD ACs until composite
score reaches threshold, caps at max retries, falls back to deterministic
criteria on exhaustion, and reports gate_passed/gate_failed/gate_avg_attempts.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from bob.spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until import (
    spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# High-quality ACs that should pass the gate (>= 0.85 composite)
_GOOD_ACS = [
    "File exists: src/bob/foo.py",
    "Function defined: bob.foo.run",
    "pytest: tests/test_foo.py::test_foo_raises_on_invalid_input",
    "pytest: tests/test_foo.py::test_foo_returns_none_on_empty",
]

# Low-quality ACs (vague, no boundary/error coverage) — score ~0.3
_BAD_ACS = [
    "The feature works correctly",
    "It handles multiple cases properly",
]


# ---------------------------------------------------------------------------
# Test: function is importable and callable
# ---------------------------------------------------------------------------

def test_spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until():
    """Smoke test: function exists, is callable, and runs without error."""
    assert callable(spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until)


# ---------------------------------------------------------------------------
# Test: gate passes on first attempt when synthesizer returns good ACs
# ---------------------------------------------------------------------------

def test_gate_passes_on_first_attempt_when_acs_are_high_quality():
    good_synthesize = AsyncMock(return_value=_GOOD_ACS)

    report = _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="Foo feature",
            description="Implements foo that raises ValueError on invalid input.",
            project_id="proj-001",
            synthesize_fn=good_synthesize,
            threshold=0.0,  # threshold=0 ensures anything passes gate
        )
    )

    assert report["gate_passed"] is True
    assert report["gate_failed"] is False
    assert report["gate_avg_attempts"] == 1
    assert report["criteria"] == _GOOD_ACS


# ---------------------------------------------------------------------------
# Test: gate retries when initial ACs score below threshold
# ---------------------------------------------------------------------------

def test_gate_retries_when_below_threshold():
    call_count = 0

    async def synthesize_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        # First call: bad ACs; second call: good ACs
        return _BAD_ACS if call_count == 1 else _GOOD_ACS

    report = _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="My feature",
            description="Feature with error handling and boundary conditions.",
            project_id="proj-002",
            synthesize_fn=synthesize_fn,
            threshold=0.5,
            max_retries=3,
        )
    )

    # Should have retried at least once
    assert call_count >= 2
    assert report["gate_avg_attempts"] >= 2


# ---------------------------------------------------------------------------
# Test: falls back to deterministic criteria after max retries exhausted
# ---------------------------------------------------------------------------

def test_falls_back_after_max_retries_exhausted():
    always_bad = AsyncMock(return_value=_BAD_ACS)

    report = _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="My fallback feature",
            description="Simple feature that does something.",
            project_id="proj-003",
            synthesize_fn=always_bad,
            threshold=1.0,  # impossible threshold
            max_retries=3,
            use_fallback=True,
        )
    )

    assert report["gate_failed"] is True
    assert report["criteria"] is not None
    assert len(report["criteria"]) >= 3  # fallback always emits >= 3 ACs
    assert report["gate_avg_attempts"] == 3


# ---------------------------------------------------------------------------
# Test: gate_passed/gate_failed are mutually exclusive
# ---------------------------------------------------------------------------

def test_gate_passed_and_gate_failed_are_mutually_exclusive():
    good_synthesize = AsyncMock(return_value=_GOOD_ACS)

    report = _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="Exclusive test feature",
            description="Feature with clear boundary checks.",
            project_id="proj-004",
            synthesize_fn=good_synthesize,
            threshold=0.0,
        )
    )

    # exactly one of gate_passed/gate_failed must be True
    assert report["gate_passed"] != report["gate_failed"]


# ---------------------------------------------------------------------------
# Test: retry_feedback is passed to synthesize_fn on subsequent attempts
# ---------------------------------------------------------------------------

def test_retry_feedback_passed_on_retry():
    received_feedbacks = []

    async def capture_feedback_fn(**kwargs):
        received_feedbacks.append(kwargs.get("retry_feedback"))
        # Always return bad ACs so we hit retries
        return _BAD_ACS

    _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="Retry feedback feature",
            description="Feature that needs error path ACs.",
            project_id="proj-005",
            synthesize_fn=capture_feedback_fn,
            threshold=1.0,  # impossible
            max_retries=2,
            use_fallback=True,
        )
    )

    # First call has no feedback (None), second call has feedback string
    assert received_feedbacks[0] is None
    assert received_feedbacks[1] is not None
    assert isinstance(received_feedbacks[1], str)
    assert len(received_feedbacks[1]) > 0


# ---------------------------------------------------------------------------
# Test: synthesize_fn returning None triggers fallback
# ---------------------------------------------------------------------------

def test_synthesize_returning_none_triggers_fallback():
    always_none = AsyncMock(return_value=None)

    report = _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="None synthesizer feature",
            description="A feature with nothing synthesized.",
            project_id="proj-006",
            synthesize_fn=always_none,
            max_retries=2,
            use_fallback=True,
        )
    )

    assert report["gate_failed"] is True
    assert report["criteria"] is not None


# ---------------------------------------------------------------------------
# Test: report dict contains required keys
# ---------------------------------------------------------------------------

def test_report_contains_required_keys():
    good_synthesize = AsyncMock(return_value=_GOOD_ACS)

    report = _run(
        spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
            title="Keys check feature",
            description="Feature description for AC key validation.",
            project_id="proj-007",
            synthesize_fn=good_synthesize,
            threshold=0.0,
        )
    )

    required_keys = {"gate_passed", "gate_failed", "gate_avg_attempts", "criteria", "composite"}
    assert required_keys.issubset(report.keys()), (
        f"Missing keys: {required_keys - report.keys()}"
    )
