"""Tests for spec_quality_gate.allowlist.is_feature_allowlisted.

Verifies that the allowlist correctly exempts permanent forward-carry infra
features from the 0.85 spec_quality_score gate while blocking regular features.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality_gate.allowlist import is_feature_allowlisted, load_allowlist_patterns


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


# ── is_feature_allowlisted: happy-path ──────────────────────────────────────

def test_f_r7_478_in_spec_slot_is_allowlisted():
    """F-R7-478 (unlimited spawn retry) in spec_slot is exempt."""
    feature = _make_feature(spec_slot="F-R7-478")
    assert is_feature_allowlisted(feature) is True


def test_f_r7_479_in_spec_slot_is_allowlisted():
    """F-R7-479 (RCA-layer NH auto-reset) in spec_slot is exempt."""
    feature = _make_feature(spec_slot="F-R7-479")
    assert is_feature_allowlisted(feature) is True


def test_f_r7_481_in_spec_slot_is_allowlisted():
    """F-R7-481 (slopsquatting local-module exclusion) in spec_slot is exempt."""
    feature = _make_feature(spec_slot="F-R7-481")
    assert is_feature_allowlisted(feature) is True


def test_f_r7_478_in_name_is_allowlisted():
    """F-R7-478 in feature name is exempt even without spec_slot."""
    feature = _make_feature(name="F-R7-478 unlimited spawn retry", spec_slot=None)
    assert is_feature_allowlisted(feature) is True


def test_permanent_forward_carry_flag_exempts_feature():
    """permanent_forward_carry=True always exempts, regardless of patterns."""
    feature = _make_feature(name="Some Brand New Feature", permanent_forward_carry=True)
    assert is_feature_allowlisted(feature) is True


def test_non_allowlisted_feature_not_exempt():
    """A regular synthesized feature is NOT exempt."""
    feature = _make_feature(name="Brand new synthesized feature", spec_slot=None)
    assert is_feature_allowlisted(feature) is False


def test_returns_bool_type():
    """Return value is always a bool (not a truthy object)."""
    feature = _make_feature(spec_slot="F-R7-478")
    result = is_feature_allowlisted(feature)
    assert isinstance(result, bool)


def test_non_matching_spec_slot_returns_false():
    """A different F-R7 slot that is not in the allowlist returns False."""
    feature = _make_feature(spec_slot="F-R7-999", name="Some Other Feature")
    assert is_feature_allowlisted(feature) is False


# ── keyword-argument API ────────────────────────────────────────────────────

def test_keyword_spec_slot_allowlisted():
    """is_feature_allowlisted works with keyword spec_slot argument."""
    result = is_feature_allowlisted(spec_slot="F-R7-478")
    assert result is True


def test_keyword_feature_name_allowlisted():
    """is_feature_allowlisted works with keyword feature_name argument."""
    result = is_feature_allowlisted(feature_name="F-R7-479 auto-reset feature")
    assert result is True


def test_keyword_permanent_forward_carry_true():
    """is_feature_allowlisted returns True when permanent_forward_carry=True via kwarg."""
    result = is_feature_allowlisted(permanent_forward_carry=True)
    assert result is True


def test_keyword_all_defaults_returns_false():
    """All keyword defaults (empty names/False flag) returns False."""
    result = is_feature_allowlisted(feature_name="random feature", spec_slot="F-R7-999")
    assert result is False


# ── load_allowlist_patterns ─────────────────────────────────────────────────

def test_default_patterns_contain_canonical_three():
    """Default allowlist contains F-R7-478, F-R7-479, F-R7-481."""
    patterns = load_allowlist_patterns()
    assert "F-R7-478" in patterns
    assert "F-R7-479" in patterns
    assert "F-R7-481" in patterns


def test_env_var_overrides_defaults(monkeypatch):
    """BOB3_ALLOWLIST_PATTERNS env var replaces the default allowlist."""
    monkeypatch.setenv("BOB3_ALLOWLIST_PATTERNS", "F-R7-999,F-R7-777")
    patterns = load_allowlist_patterns()
    assert "F-R7-999" in patterns
    assert "F-R7-777" in patterns
    assert "F-R7-478" not in patterns


def test_env_var_deduplicates(monkeypatch):
    """Duplicate entries in BOB3_ALLOWLIST_PATTERNS are deduplicated."""
    monkeypatch.setenv("BOB3_ALLOWLIST_PATTERNS", "F-R7-478,F-R7-478,F-R7-479")
    patterns = load_allowlist_patterns()
    assert patterns.count("F-R7-478") == 1


def test_custom_pattern_via_env_exempts_feature(monkeypatch):
    """A custom allowlist pattern set via env var exempts a matching feature."""
    monkeypatch.setenv("BOB3_ALLOWLIST_PATTERNS", "CUSTOM-INFRA-FEATURE")
    feature = _make_feature(name="CUSTOM-INFRA-FEATURE some description")
    assert is_feature_allowlisted(feature) is True


# ── error paths ────────────────────────────────────────────────────────────

def test_none_feature_without_kwargs_returns_false():
    """None passed without keyword args (all defaults) returns False, does not raise."""
    result = is_feature_allowlisted()
    assert result is False


def test_integer_feature_raises_value_error():
    """Passing an int as feature raises ValueError."""
    with pytest.raises(ValueError, match="primitive"):
        is_feature_allowlisted(42)  # type: ignore[arg-type]


def test_string_feature_raises_value_error():
    """Passing a bare string as feature raises ValueError."""
    with pytest.raises(ValueError, match="primitive"):
        is_feature_allowlisted("F-R7-478")  # type: ignore[arg-type]


def test_dict_feature_raises_value_error():
    """Passing a plain dict as feature raises ValueError."""
    with pytest.raises(ValueError, match="primitive"):
        is_feature_allowlisted({})  # type: ignore[arg-type]
