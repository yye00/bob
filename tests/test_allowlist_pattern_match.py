"""Tests for spec_quality_allowlist.load_allowlist_patterns and is_permanent_forward_carry pattern matching."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch


def _make_feature(**kwargs):
    """Return a minimal Feature-like object for testing."""
    from bob.models import Feature
    defaults = dict(
        id="aaaaaaaa-0000-0000-0000-000000000001",
        project_id="proj-1",
        name="Test feature",
        status="pending",
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestLoadAllowlistPatterns:
    def test_returns_list(self):
        from bob.spec_quality_allowlist import load_allowlist_patterns
        patterns = load_allowlist_patterns()
        assert isinstance(patterns, list)

    def test_each_pattern_is_string(self):
        from bob.spec_quality_allowlist import load_allowlist_patterns
        patterns = load_allowlist_patterns()
        for p in patterns:
            assert isinstance(p, str)

    def test_env_var_override_adds_patterns(self):
        from bob.spec_quality_allowlist import load_allowlist_patterns
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": "F-R7-478,F-R7-479"}):
            patterns = load_allowlist_patterns()
        assert "F-R7-478" in patterns
        assert "F-R7-479" in patterns

    def test_env_var_empty_string_returns_defaults(self):
        from bob.spec_quality_allowlist import load_allowlist_patterns
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": ""}):
            patterns = load_allowlist_patterns()
        assert isinstance(patterns, list)

    def test_default_patterns_include_known_infra_slots(self):
        """The default allowlist must include the three known infra slots."""
        from bob.spec_quality_allowlist import load_allowlist_patterns
        patterns = load_allowlist_patterns()
        assert "F-R7-478" in patterns
        assert "F-R7-479" in patterns
        assert "F-R7-481" in patterns


class TestIsPermanentForwardCarryPatternMatch:
    def test_feature_with_matching_spec_slot_returns_true(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot="F-R7-478")
        assert is_permanent_forward_carry(feature) is True

    def test_feature_with_non_matching_spec_slot_returns_false(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot="F-R7-999")
        assert is_permanent_forward_carry(feature) is False

    def test_feature_with_no_spec_slot_but_matching_name_returns_true(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot=None, name="F-R7-478 unlimited spawn retry")
        assert is_permanent_forward_carry(feature) is True

    def test_feature_with_no_spec_slot_no_match_returns_false(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot=None, name="some random feature")
        assert is_permanent_forward_carry(feature) is False

    def test_permanent_forward_carry_flag_true_returns_true(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(permanent_forward_carry=True, spec_slot=None)
        assert is_permanent_forward_carry(feature) is True

    def test_permanent_forward_carry_flag_false_with_no_slot_returns_false(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(permanent_forward_carry=False, spec_slot=None, name="normal feature")
        assert is_permanent_forward_carry(feature) is False

    def test_partial_spec_slot_match_is_substring(self):
        """Pattern 'F-R7-478' should match spec_slot containing that substring."""
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot="F-R7-478")
        assert is_permanent_forward_carry(feature) is True

    def test_env_override_pattern_is_respected(self):
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot="F-R7-999")
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": "F-R7-999"}):
            result = is_permanent_forward_carry(feature)
        assert result is True
