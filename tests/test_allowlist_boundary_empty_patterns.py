"""Boundary tests for spec_quality_allowlist with empty/minimal pattern sets."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch


def _make_feature(**kwargs):
    from bob.models import Feature
    defaults = dict(
        id="bbbbbbbb-0000-0000-0000-000000000002",
        project_id="proj-1",
        name="Test feature",
        status="pending",
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestEmptyAndBoundaryPatterns:
    def test_empty_pattern_list_env_var_no_match(self):
        """With empty override and no flag, a random feature is not exempt."""
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot="F-R7-999", name="some feature")
        # Override to empty list (no comma-separated items)
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": ""}):
            result = is_permanent_forward_carry(feature)
        # Empty env override means fall back to defaults which do not include F-R7-999
        assert result is False

    def test_none_feature_id_does_not_crash(self):
        """Feature with all None optional fields does not raise."""
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot=None, name="")
        result = is_permanent_forward_carry(feature)
        assert isinstance(result, bool)

    def test_pattern_with_whitespace_stripped(self):
        """Patterns with surrounding whitespace in env var are stripped."""
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot="F-R7-478")
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": " F-R7-478 , F-R7-479 "}):
            result = is_permanent_forward_carry(feature)
        assert result is True

    def test_load_allowlist_patterns_always_returns_list_type(self):
        """load_allowlist_patterns always returns list, never None."""
        from bob.spec_quality_allowlist import load_allowlist_patterns
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": ""}):
            result = load_allowlist_patterns()
        assert result is not None
        assert isinstance(result, list)

    def test_feature_with_empty_name_and_no_slot_is_not_carry(self):
        """Feature with empty name and no spec_slot is never a carry."""
        from bob.spec_quality_allowlist import is_permanent_forward_carry
        feature = _make_feature(spec_slot=None, name="")
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": ""}):
            result = is_permanent_forward_carry(feature)
        assert result is False

    def test_single_pattern_env_var(self):
        """Single pattern without comma separator works."""
        from bob.spec_quality_allowlist import load_allowlist_patterns
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": "F-R7-478"}):
            patterns = load_allowlist_patterns()
        assert "F-R7-478" in patterns
        assert len(patterns) == 1

    def test_duplicate_patterns_deduplicated(self):
        """Duplicate entries in env var are deduplicated."""
        from bob.spec_quality_allowlist import load_allowlist_patterns
        with patch.dict(os.environ, {"BOB_ALLOWLIST_PATTERNS": "F-R7-478,F-R7-478"}):
            patterns = load_allowlist_patterns()
        assert patterns.count("F-R7-478") == 1
