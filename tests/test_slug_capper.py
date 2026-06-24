"""Tests for bob.slug_capper.cap_slug_at_boundary.

Feature d428fc62-25bc-4022-a373-d33628f5e1fa

Verifies that cap_slug_at_boundary correctly caps slugs at whole-token
boundaries so that the derived .py filename never exceeds the filesystem's
255-byte NAME_MAX limit.
"""

from __future__ import annotations

import pytest

from bob.slug_capper import cap_slug_at_boundary


class TestCapSlugAtBoundaryShortSlugs:
    """Slugs already within the cap pass through unchanged."""

    def test_short_slug_unchanged(self) -> None:
        assert cap_slug_at_boundary("foo") == "foo"

    def test_exactly_60_chars_unchanged(self) -> None:
        slug = "a" * 60
        assert cap_slug_at_boundary(slug) == slug

    def test_multi_token_short_unchanged(self) -> None:
        slug = "foo_bar_baz"
        assert cap_slug_at_boundary(slug) == slug

    def test_single_char_unchanged(self) -> None:
        assert cap_slug_at_boundary("x") == "x"


class TestCapSlugAtBoundaryLongSlugs:
    """Slugs exceeding the cap are truncated on whole-token boundaries."""

    def test_61_char_slug_capped(self) -> None:
        slug = "a" * 61
        result = cap_slug_at_boundary(slug)
        assert len(result) <= 60

    def test_long_multi_token_slug_capped_at_whole_token(self) -> None:
        # 3 tokens of 20 chars → 20+1+20+1+20 = 62 chars → must be capped
        tok = "b" * 20
        slug = f"{tok}_{tok}_{tok}"
        result = cap_slug_at_boundary(slug)
        assert len(result) <= 60
        # Result should be whole tokens (no partial tokens from the middle)
        assert not result.endswith("_")

    def test_200_char_slug_capped(self) -> None:
        # Simulate the real-world hung-run scenario: 200+ char title slug
        tokens = ["word"] * 50  # 50 * 4 + 49 = 249 chars
        slug = "_".join(tokens)
        assert len(slug) > 200
        result = cap_slug_at_boundary(slug)
        assert len(result) <= 60

    def test_long_slug_preserves_leading_tokens(self) -> None:
        slug = "alpha_beta_gamma_" + "x" * 50
        result = cap_slug_at_boundary(slug)
        assert result.startswith("alpha")
        assert len(result) <= 60

    def test_custom_max_len(self) -> None:
        slug = "foo_bar_baz_qux"
        result = cap_slug_at_boundary(slug, max_len=10)
        assert len(result) <= 10

    def test_exactly_cap_boundary(self) -> None:
        # 4 tokens of 14 chars each: 14+1+14+1+14+1+14 = 59, then "z" → 61
        tok14 = "a" * 14
        slug = f"{tok14}_{tok14}_{tok14}_{tok14}_z"
        result = cap_slug_at_boundary(slug)
        assert len(result) <= 60

    def test_single_overlong_token_hard_truncated(self) -> None:
        # A single token > 60 chars cannot be split on token boundaries
        slug = "x" * 80
        result = cap_slug_at_boundary(slug)
        assert len(result) <= 60
        assert len(result) > 0


class TestCapSlugAtBoundaryInvalidInputs:
    """Invalid inputs raise ValueError."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            cap_slug_at_boundary("")

    def test_none_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            cap_slug_at_boundary(None)  # type: ignore[arg-type]

    def test_integer_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            cap_slug_at_boundary(42)  # type: ignore[arg-type]

    def test_max_len_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            cap_slug_at_boundary("foo", max_len=0)

    def test_max_len_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            cap_slug_at_boundary("foo", max_len=-1)


class TestCapSlugAtBoundaryReturnType:
    """Return value is always a non-empty string."""

    def test_returns_string(self) -> None:
        result = cap_slug_at_boundary("hello_world")
        assert isinstance(result, str)

    def test_result_not_empty(self) -> None:
        result = cap_slug_at_boundary("hello_world_this_is_a_long_slug_" + "x" * 40)
        assert len(result) > 0

    def test_no_trailing_underscore(self) -> None:
        tok20 = "c" * 20
        slug = f"{tok20}_{tok20}_{tok20}"
        result = cap_slug_at_boundary(slug)
        assert not result.endswith("_")
