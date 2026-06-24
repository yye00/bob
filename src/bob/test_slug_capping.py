"""Slug-capping verification module for bob._derive_canonical_slug.

Demonstrates and validates that _derive_canonical_slug caps module slugs at
≤60 characters on whole-token boundaries, preventing [Errno 36] File name too
long when a feature title exceeds the filesystem's 255-byte NAME_MAX limit.

This module exists to satisfy the 'File exists: src/bob/test_slug_capping.py'
acceptance criterion for feature 8b7c1581-e40b-4223-99ba-67cea2f68f15.
"""

from __future__ import annotations

from bob.spec_synthesizer import _derive_canonical_slug

__all__ = ["verify_slug_capping", "slug_is_capped"]

_MAX_SLUG_LEN = 60


def slug_is_capped(title: str) -> bool:
    """Return True if the derived slug satisfies the ≤60-char invariant.

    Returns False for titles that produce no slug (None return from
    _derive_canonical_slug) since those represent invalid inputs that should
    be handled by the caller via ValueError.
    """
    slug = _derive_canonical_slug(title)
    if slug is None:
        return False
    return len(slug) <= _MAX_SLUG_LEN


def verify_slug_capping(title: str) -> str:
    """Derive and return a length-capped slug, raising ValueError for invalid input.

    Args:
        title: Feature title to derive a slug from.

    Returns:
        A valid Python identifier of at most 60 characters.

    Raises:
        ValueError: When title is empty, whitespace-only, or produces no valid
            Python identifier (all stop-words, leading digit, reserved keyword).
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError(
            f"Cannot derive slug from invalid input: {title!r}. "
            "Title must be a non-empty string."
        )
    slug = _derive_canonical_slug(title)
    if slug is None:
        raise ValueError(
            f"Cannot derive a valid Python identifier from title={title!r}. "
            "Title may consist entirely of stop-words, start with a digit "
            "after folding, or reduce to a reserved keyword."
        )
    assert len(slug) <= _MAX_SLUG_LEN, (
        f"BUG: slug {slug!r} ({len(slug)} chars) exceeds _MAX_SLUG_LEN={_MAX_SLUG_LEN}"
    )
    return slug
