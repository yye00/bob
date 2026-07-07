"""Tests for bob.spec_quality_gate_allowlist — the AC-required module.

Verifies is_permanent_forward_carry and bypass_quality_gate correctly exempt
permanent forward-carry infra features from the 0.85 spec_quality_score gate.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.spec_quality_gate_allowlist import (
    bypass_quality_gate,
    is_permanent_forward_carry,
)


def _make_feature(
    name: str = "Test Feature",
    spec_slot: str | None = None,
    permanent_forward_carry: bool = False,
) -> MagicMock:
    feature = MagicMock()
    feature.name = name
    feature.spec_slot = spec_slot
    feature.permanent_forward_carry = permanent_forward_carry
    return feature


# ── is_permanent_forward_carry ──────────────────────────────────────────────

def test_f_r7_478_slot_is_forward_carry():
    assert is_permanent_forward_carry(_make_feature(spec_slot="F-R7-478")) is True


def test_f_r7_479_slot_is_forward_carry():
    assert is_permanent_forward_carry(_make_feature(spec_slot="F-R7-479")) is True


def test_f_r7_481_slot_is_forward_carry():
    assert is_permanent_forward_carry(_make_feature(spec_slot="F-R7-481")) is True


def test_flag_alone_is_forward_carry():
    feature = _make_feature(name="New", spec_slot=None, permanent_forward_carry=True)
    assert is_permanent_forward_carry(feature) is True


def test_regular_feature_is_not_forward_carry():
    assert is_permanent_forward_carry(_make_feature(spec_slot="F-R7-999")) is False


def test_is_permanent_forward_carry_returns_bool():
    assert isinstance(is_permanent_forward_carry(_make_feature(spec_slot="F-R7-478")), bool)


# ── bypass_quality_gate ─────────────────────────────────────────────────────

def test_bypass_true_for_allowlisted_slot():
    assert bypass_quality_gate(_make_feature(spec_slot="F-R7-478")) is True


def test_bypass_false_for_regular_feature():
    assert bypass_quality_gate(_make_feature(spec_slot="F-R7-999")) is False


def test_bypass_true_for_flag():
    feature = _make_feature(name="New", permanent_forward_carry=True)
    assert bypass_quality_gate(feature) is True


def test_bypass_returns_bool():
    assert isinstance(bypass_quality_gate(_make_feature(spec_slot="F-R7-478")), bool)


# ── boundary ────────────────────────────────────────────────────────────────

def test_empty_fields_returns_false():
    feature = _make_feature(name="", spec_slot=None, permanent_forward_carry=False)
    assert is_permanent_forward_carry(feature) is False
    assert bypass_quality_gate(feature) is False


def test_empty_spec_slot_string_returns_false():
    feature = _make_feature(name="x", spec_slot="", permanent_forward_carry=False)
    assert bypass_quality_gate(feature) is False


# ── error paths ─────────────────────────────────────────────────────────────

def test_none_raises_value_error():
    with pytest.raises(ValueError, match="feature"):
        is_permanent_forward_carry(None)  # type: ignore[arg-type]


def test_bypass_none_raises_value_error():
    with pytest.raises(ValueError, match="feature"):
        bypass_quality_gate(None)  # type: ignore[arg-type]


def test_int_raises():
    with pytest.raises((ValueError, AttributeError, TypeError)):
        is_permanent_forward_carry(42)  # type: ignore[arg-type]


def test_bypass_int_raises():
    with pytest.raises((ValueError, AttributeError, TypeError)):
        bypass_quality_gate(42)  # type: ignore[arg-type]
