"""Tests for bob.spec_quality_gate_permanent_carry_allowlist.

Verifies that permanent forward-carry infrastructure features (F-R7-478,
F-R7-479, F-R7-481) bypass the 0.85 spec_quality_score gate, while normal
newly-synthesized features do not.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.spec_quality_gate_permanent_carry_allowlist import (
    bypass_quality_gate,
    is_permanent_forward_carry,
    load_allowlist_patterns,
)


def _make_feature(**kwargs) -> MagicMock:
    feature = MagicMock()
    feature.name = kwargs.get("name", "")
    feature.spec_slot = kwargs.get("spec_slot", None)
    feature.permanent_forward_carry = kwargs.get("permanent_forward_carry", False)
    return feature


def test_explicit_flag_bypasses_gate():
    feature = _make_feature(permanent_forward_carry=True)
    assert is_permanent_forward_carry(feature) is True
    assert bypass_quality_gate(feature) is True


def test_f_r7_478_spec_slot_is_exempt():
    feature = _make_feature(spec_slot="F-R7-478")
    assert is_permanent_forward_carry(feature) is True
    assert bypass_quality_gate(feature) is True


def test_f_r7_479_in_name_is_exempt():
    feature = _make_feature(name="F-R7-479 RCA-layer NH auto-reset")
    assert is_permanent_forward_carry(feature) is True


def test_f_r7_481_spec_slot_is_exempt():
    feature = _make_feature(spec_slot="F-R7-481")
    assert is_permanent_forward_carry(feature) is True


def test_normal_feature_not_exempt():
    feature = _make_feature(name="add new widget", spec_slot="F-R9-001")
    assert is_permanent_forward_carry(feature) is False
    assert bypass_quality_gate(feature) is False


def test_bypass_matches_is_permanent_forward_carry():
    for slot in ("F-R7-478", "F-R9-100", "F-R7-481"):
        feature = _make_feature(spec_slot=slot)
        assert bypass_quality_gate(feature) == is_permanent_forward_carry(feature)


def test_load_allowlist_patterns_contains_defaults():
    patterns = load_allowlist_patterns()
    assert "F-R7-478" in patterns
    assert "F-R7-479" in patterns
    assert "F-R7-481" in patterns


def test_env_override_extends_allowlist(monkeypatch):
    monkeypatch.setenv("BOB_ALLOWLIST_PATTERNS", "F-R7-999")
    patterns = load_allowlist_patterns()
    assert "F-R7-999" in patterns
    feature = _make_feature(spec_slot="F-R7-999")
    assert is_permanent_forward_carry(feature) is True


def test_return_type_is_bool():
    feature = _make_feature(spec_slot="F-R7-478")
    assert isinstance(is_permanent_forward_carry(feature), bool)
    assert isinstance(bypass_quality_gate(feature), bool)


def test_none_raises_value_error():
    with pytest.raises(ValueError, match="feature"):
        is_permanent_forward_carry(None)  # type: ignore[arg-type]


def test_primitive_raises_value_error():
    with pytest.raises(ValueError):
        bypass_quality_gate(42)  # type: ignore[arg-type]


def test_integration_matches_canonical_gate():
    from bob.spec_quality_gate import bypass_quality_threshold

    feature = _make_feature(spec_slot="F-R7-478")
    assert bypass_quality_gate(feature) == bypass_quality_threshold(feature)
