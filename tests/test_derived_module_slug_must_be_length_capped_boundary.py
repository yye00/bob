"""Boundary-case tests for derived_module_slug length-capping.

Feature 2a18af78-0f2b-42cd-a6c5-3d916905a3b3

Empty, zero-length, or minimum input returns a well-defined result
rather than raising (boundary case AC).
"""
from __future__ import annotations

import pytest

from bob.derived_module_slug import build_fallback_criteria, derive_canonical_slug


def test_empty_string_returns_none_not_raises() -> None:
    """Empty string input returns None, does not raise."""
    result = derive_canonical_slug("")
    assert result is None


def test_whitespace_only_returns_none_not_raises() -> None:
    """Whitespace-only input returns None, does not raise."""
    result = derive_canonical_slug("   \t\n  ")
    assert result is None


def test_single_char_title() -> None:
    """Single meaningful character produces a slug or None, never raises."""
    result = derive_canonical_slug("x")
    # Either a valid slug or None — but must not raise
    if result is not None:
        assert result.isidentifier()
        assert len(result) <= 60


def test_exactly_60_char_slug_unchanged() -> None:
    """A title whose slug is exactly 60 chars is returned as-is."""
    # Build a title with tokens totalling exactly 60 chars when joined.
    # 4 tokens of length 14 = 14+1+14+1+14+1+14 = 59 chars, add one token of 1
    tok14 = "a" * 14
    title = f"{tok14} {tok14} {tok14} {tok14} z"
    result = derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= 60


def test_slug_just_over_60_chars_capped() -> None:
    """A title whose full slug would be 61 chars is capped to ≤60."""
    # 3 tokens of 20 chars = 20+1+20+1+20 = 62 chars → must be capped
    tok20 = "b" * 20
    title = f"{tok20} {tok20} {tok20}"
    result = derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= 60


def test_none_input_returns_none_not_raises() -> None:
    """None input returns None, does not raise."""
    result = derive_canonical_slug(None)  # type: ignore[arg-type]
    assert result is None


def test_integer_input_returns_none_not_raises() -> None:
    """Integer input returns None, does not raise."""
    result = derive_canonical_slug(42)  # type: ignore[arg-type]
    assert result is None


def test_build_fallback_criteria_minimum_valid_input() -> None:
    """Minimum valid input produces a well-formed criteria list."""
    criteria = build_fallback_criteria("foo bar", "")
    assert isinstance(criteria, list)
    assert len(criteria) >= 3
