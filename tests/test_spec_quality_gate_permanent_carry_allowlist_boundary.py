"""Boundary case tests for bob72.spec_quality_gate.check_allowlist.

Verifies that empty, zero, or minimum input returns a well-defined result
rather than raising.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob72.spec_quality_gate import check_allowlist


def _make_feature(**kwargs) -> MagicMock:
    feature = MagicMock()
    feature.name = kwargs.get("name", "")
    feature.spec_slot = kwargs.get("spec_slot", None)
    feature.permanent_forward_carry = kwargs.get("permanent_forward_carry", False)
    return feature


def test_empty_name_and_no_slot_returns_false():
    """Empty string name with no spec_slot should return False without raising."""
    feature = _make_feature(name="", spec_slot=None, permanent_forward_carry=False)
    result = check_allowlist(feature)
    assert result is False


def test_empty_spec_slot_string_returns_false():
    """Empty string spec_slot should return False without raising."""
    feature = _make_feature(name="some feature", spec_slot="", permanent_forward_carry=False)
    result = check_allowlist(feature)
    assert result is False


def test_both_fields_empty_strings_returns_false():
    """Feature with empty name and empty spec_slot — well-defined False, no exception."""
    feature = _make_feature(name="", spec_slot="", permanent_forward_carry=False)
    result = check_allowlist(feature)
    assert result is False


def test_none_spec_slot_with_empty_name_returns_false():
    """Minimum input: all empty/None/False. Must return False, not raise."""
    feature = _make_feature(name="", spec_slot=None, permanent_forward_carry=False)
    result = check_allowlist(feature)
    assert result is False


def test_permanent_forward_carry_true_with_empty_fields_returns_true():
    """Flag alone is sufficient — empty name/slot + flag=True should return True."""
    feature = _make_feature(name="", spec_slot=None, permanent_forward_carry=True)
    result = check_allowlist(feature)
    assert result is True


def test_spec_slot_whitespace_only_returns_false():
    """Whitespace-only spec_slot should not match any pattern; return False."""
    feature = _make_feature(name="   ", spec_slot="   ", permanent_forward_carry=False)
    result = check_allowlist(feature)
    assert result is False


def test_returns_bool_on_minimum_input():
    """Return must be bool even with minimum/empty input, not a truthy object."""
    feature = _make_feature(name="", spec_slot=None, permanent_forward_carry=False)
    result = check_allowlist(feature)
    assert isinstance(result, bool)
