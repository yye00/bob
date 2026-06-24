"""Tests for spec_quality_gate_permanent_carry_allowlist_exempt_forward module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.spec_quality_gate_permanent_carry_allowlist_exempt_forward import (
    spec_quality_gate_permanent_carry_allowlist_exempt_forward,
)


def _make_feature(
    name: str = "Test Feature",
    spec_slot: str | None = None,
    permanent_forward_carry: bool = False,
    description: str = "A test feature description.",
    acceptance_criteria: list[str] | None = None,
) -> MagicMock:
    feature = MagicMock()
    feature.name = name
    feature.spec_slot = spec_slot
    feature.permanent_forward_carry = permanent_forward_carry
    feature.description = description
    feature.acceptance_criteria = acceptance_criteria or []
    return feature


def test_spec_quality_gate_permanent_carry_allowlist_exempt_forward():
    """Core AC: function exists, exempt forward-carry features bypass the gate and return True."""
    feature = _make_feature(
        name="F-R7-478 unlimited spawn retry",
        spec_slot="F-R7-478",
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True, "Forward-carry feature should be exempt (bypass=True)"


def test_non_allowlisted_feature_not_exempt():
    """A regular feature (not in allowlist, no flag) must NOT be exempted."""
    feature = _make_feature(
        name="Some brand new synthesized feature",
        spec_slot=None,
        permanent_forward_carry=False,
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is False, "Non-allowlisted feature should not be exempt"


def test_permanent_forward_carry_flag_exempts():
    """A feature with permanent_forward_carry=True must be exempt regardless of name/spec_slot."""
    feature = _make_feature(
        name="Random infra feature",
        spec_slot=None,
        permanent_forward_carry=True,
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True, "Feature with permanent_forward_carry flag must be exempt"


def test_spec_slot_f_r7_479_exempt():
    """F-R7-479 (RCA-layer NH auto-reset) must be exempt via spec_slot match."""
    feature = _make_feature(
        name="RCA auto-reset feature",
        spec_slot="F-R7-479",
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True


def test_spec_slot_f_r7_481_exempt():
    """F-R7-481 (slopsquatting local-module exclusion) must be exempt via spec_slot match."""
    feature = _make_feature(
        name="Slopsquatting exclusion",
        spec_slot="F-R7-481",
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True


def test_name_contains_allowlist_pattern_exempt():
    """A feature whose name contains an allowlisted pattern must be exempt."""
    feature = _make_feature(
        name="F-R7-478 equivalent retry infrastructure",
        spec_slot=None,
        permanent_forward_carry=False,
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True


def test_unknown_spec_slot_not_exempt():
    """A feature with a spec_slot that does not match any allowlist pattern must not be exempt."""
    feature = _make_feature(
        name="Some new feature",
        spec_slot="F-R7-999",
        permanent_forward_carry=False,
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is False


def test_returns_bool():
    """Function must return a plain bool, not a truthy object."""
    for carry_flag in (True, False):
        feature = _make_feature(permanent_forward_carry=carry_flag)
        result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"


def test_env_override_allowlist(monkeypatch):
    """BOB_ALLOWLIST_PATTERNS env var must extend the allowlist."""
    monkeypatch.setenv("BOB_ALLOWLIST_PATTERNS", "CUSTOM-001,CUSTOM-002")
    feature = _make_feature(
        name="Custom infra CUSTOM-001",
        spec_slot=None,
        permanent_forward_carry=False,
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True, "Custom pattern from env var must be honored"


def test_empty_env_allowlist_falls_back_to_defaults(monkeypatch):
    """Empty BOB_ALLOWLIST_PATTERNS must fall back to hardcoded defaults."""
    monkeypatch.setenv("BOB_ALLOWLIST_PATTERNS", "")
    feature = _make_feature(
        name="F-R7-478 feature",
        spec_slot="F-R7-478",
        permanent_forward_carry=False,
    )
    result = spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature)
    assert result is True, "Default allowlist should still apply when env is empty"
