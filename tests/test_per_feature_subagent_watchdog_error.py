"""Error-path tests for bob.feature_watchdog (per-feature subagent watchdog).

AC: invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from bob.orchestrator.feature_watchdog import compute_deadline
from bob.feature_watchdog import spawn_feature_watchdog

FEATURE_ID = "110b0899-09c3-4eab-b4f0-b29a6b0a764d"
TEST_PID = 99999


def test_compute_deadline_zero_raises_value_error():
    """compute_deadline(0) must raise ValueError — zero is not a valid timeout."""
    with pytest.raises(ValueError):
        compute_deadline(0)


def test_compute_deadline_negative_raises_value_error():
    """compute_deadline with a negative value must raise ValueError."""
    with pytest.raises(ValueError):
        compute_deadline(-1)


def test_compute_deadline_large_negative_raises_value_error():
    """compute_deadline(-9999) must raise ValueError."""
    with pytest.raises(ValueError):
        compute_deadline(-9999)


def test_compute_deadline_negative_float_raises_value_error():
    """compute_deadline(-0.001) must raise ValueError."""
    with pytest.raises(ValueError):
        compute_deadline(-0.001)


def test_compute_deadline_error_message_contains_value():
    """ValueError message from compute_deadline must include the bad value."""
    with pytest.raises(ValueError, match=r"-5"):
        compute_deadline(-5)
