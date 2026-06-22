"""Test: compute_deadline boundary conditions — zero and negative timeout_seconds.

Verifies that compute_deadline raises ValueError for non-positive inputs, and
returns sensible values for small positive inputs.
"""

from __future__ import annotations

import time

import pytest

from bob3.orchestrator.feature_watchdog import compute_deadline


def test_compute_deadline_raises_on_zero():
    """compute_deadline(0) must raise ValueError."""
    with pytest.raises(ValueError, match="positive"):
        compute_deadline(0)


def test_compute_deadline_raises_on_negative():
    """compute_deadline(-1) must raise ValueError."""
    with pytest.raises(ValueError, match="positive"):
        compute_deadline(-1)


def test_compute_deadline_raises_on_very_negative():
    """compute_deadline(-3600) must raise ValueError."""
    with pytest.raises(ValueError, match="positive"):
        compute_deadline(-3600)


def test_compute_deadline_positive_value():
    """compute_deadline(60) returns a future monotonic time."""
    before = time.monotonic()
    result = compute_deadline(60)
    after = time.monotonic()

    assert result >= before + 60, "Deadline must be at least 60s from before-call monotonic"
    assert result <= after + 60 + 0.1, "Deadline must not be more than 60s + epsilon from after-call monotonic"


def test_compute_deadline_small_value():
    """compute_deadline(0.001) returns a deadline just slightly in the future."""
    before = time.monotonic()
    result = compute_deadline(0.001)
    assert result > before
    assert result < before + 1.0  # well within a second


def test_compute_deadline_large_value():
    """compute_deadline(3600) returns a deadline 1 hour in the future."""
    before = time.monotonic()
    result = compute_deadline(3600)
    after = time.monotonic()

    assert result >= before + 3600
    assert result <= after + 3600 + 0.5
