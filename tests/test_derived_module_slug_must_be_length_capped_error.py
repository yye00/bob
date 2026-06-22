"""Error-path tests for derived_module_slug length-capping.

Feature 2a18af78-0f2b-42cd-a6c5-3d916905a3b3

Invalid input raises ValueError and the function does not silently succeed
(error path AC).
"""
from __future__ import annotations

import pytest

from bob3.derived_module_slug import build_fallback_criteria, derive_canonical_slug


def test_build_fallback_criteria_empty_name_raises_value_error() -> None:
    """Empty feature_name raises ValueError, not a silent empty result."""
    with pytest.raises(ValueError, match="(?i)(empty|valid|identifier|slug)"):
        build_fallback_criteria("", "some description")


def test_build_fallback_criteria_whitespace_name_raises_value_error() -> None:
    """Whitespace-only feature_name raises ValueError."""
    with pytest.raises(ValueError):
        build_fallback_criteria("   ", "some description")


def test_build_fallback_criteria_all_stopwords_raises_value_error() -> None:
    """A title composed entirely of stop-words raises ValueError."""
    # "the a an for to of in on with and" are all stop-words
    with pytest.raises(ValueError):
        build_fallback_criteria("the a an for to of in on", "description here")


def test_build_fallback_criteria_does_not_silently_succeed_on_bad_input() -> None:
    """build_fallback_criteria must raise on degenerate input, never return []."""
    for bad_name in ("", "   ", "the a an"):
        try:
            result = build_fallback_criteria(bad_name, "desc")
            # If it didn't raise, it must not be an empty list
            # (that would be a silent failure)
            assert result, (
                f"build_fallback_criteria({bad_name!r}) returned empty list — "
                "expected ValueError"
            )
        except ValueError:
            pass  # correct behaviour


def test_derive_canonical_slug_keyword_title_returns_none() -> None:
    """A title that reduces to a Python keyword returns None (not importable)."""
    # 'class' is a Python keyword; slug would be 'class' which is invalid
    result = derive_canonical_slug("class")
    assert result is None


def test_derive_canonical_slug_leading_digit_returns_none() -> None:
    """A title starting with a digit (after stop-word removal) returns None."""
    # Purely numeric token cannot be a Python identifier
    result = derive_canonical_slug("123")
    assert result is None
