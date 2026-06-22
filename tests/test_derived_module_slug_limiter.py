"""Tests for bob3.derived_module_slug_limiter.cap_slug_at_boundary.

Feature 4fdb456f-f8b5-44f3-a2bf-dbd7db4e30b3

Verifies that cap_slug_at_boundary caps derived module slugs at 60 characters
on whole-token boundaries, preventing the [Errno 36] FILE NAME TOO LONG crash
that wedged a prior generation for 7 hours.
"""
from __future__ import annotations

import pytest

from bob3.derived_module_slug_limiter import cap_slug_at_boundary


def test_short_slug_unchanged() -> None:
    """Slug within 60 chars is returned unchanged."""
    slug = "foo_bar_baz"
    assert cap_slug_at_boundary(slug) == slug


def test_exactly_60_chars_unchanged() -> None:
    """Slug of exactly 60 chars is returned unchanged."""
    slug = "a" * 60
    result = cap_slug_at_boundary(slug)
    assert result == slug
    assert len(result) == 60


def test_long_slug_capped_at_boundary() -> None:
    """Long slug is capped to ≤60 chars on a whole-token boundary."""
    tokens = ["derived", "module", "slug", "must", "be", "length", "capped",
              "long", "feature", "title", "otherwise", "yields", "py",
              "filename", "exceeding", "filesystem", "limit"]
    slug = "_".join(tokens)
    assert len(slug) > 60
    result = cap_slug_at_boundary(slug)
    assert len(result) <= 60
    # Result must be a prefix of the original slug (on token boundary)
    assert slug.startswith(result)
    assert "_" not in result or all(t in tokens for t in result.split("_"))


def test_very_long_single_token_hard_truncated() -> None:
    """A single token longer than 60 chars is hard-truncated to 60."""
    slug = "a" * 100
    result = cap_slug_at_boundary(slug)
    assert len(result) <= 60


def test_custom_max_len_respected() -> None:
    """custom max_len parameter is respected."""
    slug = "foo_bar_baz_qux"
    result = cap_slug_at_boundary(slug, max_len=7)
    assert len(result) <= 7


def test_result_is_valid_identifier_prefix() -> None:
    """Capped slug produces a valid Python identifier."""
    long_title_slug = (
        "rca_auto_reset_must_grant_fresh_attempt_budget_when_"
        "verification_gate_failure_cause_is_plausibly_fixable_code"
    )
    result = cap_slug_at_boundary(long_title_slug)
    assert len(result) <= 60
    assert result.replace("_", "").isalnum() or result.isidentifier()


def test_empty_slug_raises_value_error() -> None:
    """Empty string raises ValueError."""
    with pytest.raises(ValueError):
        cap_slug_at_boundary("")


def test_non_string_slug_raises_value_error() -> None:
    """Non-string input raises ValueError."""
    with pytest.raises(ValueError):
        cap_slug_at_boundary(None)  # type: ignore[arg-type]


def test_invalid_max_len_raises_value_error() -> None:
    """max_len < 1 raises ValueError."""
    with pytest.raises(ValueError):
        cap_slug_at_boundary("foo_bar", max_len=0)


def test_two_token_slug_capped_on_boundary() -> None:
    """Two tokens where only the first fits are capped to the first token."""
    # First token = 30 chars, second token = 35 chars => full slug 66 chars
    token1 = "a" * 30
    token2 = "b" * 35
    slug = f"{token1}_{token2}"
    result = cap_slug_at_boundary(slug, max_len=60)
    assert result == token1


def test_filename_stays_under_255_bytes() -> None:
    """The resulting <slug>.py filename stays well under 255 bytes."""
    # Simulate worst-case slug from a 200+ char feature title
    words = ["word"] * 50  # 50 tokens of 4 chars = would be 249 chars
    slug = "_".join(words)
    assert len(slug) > 60
    result = cap_slug_at_boundary(slug)
    filename = f"{result}.py"
    assert len(filename.encode()) < 255
