"""Tests for bob.slug_limiter — length-capped module slug derivation.

Feature cdc5f7fb-4e83-488b-9783-a7cfb5d0901b

Verifies that derive_canonical_slug caps slugs at ≤60 characters on whole-token
boundaries, preventing the filesystem NAME_MAX hang caused by 200+ character
feature titles.
"""
from __future__ import annotations

import pytest

from bob.slug_limiter import build_fallback_criteria, derive_canonical_slug


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------


def test_module_importable() -> None:
    """bob.slug_limiter must be importable and expose the required symbols."""
    import bob.slug_limiter as m

    assert callable(m.derive_canonical_slug)
    assert callable(m.build_fallback_criteria)


def test_short_title_returns_slug() -> None:
    """A normal short title returns a non-None slug."""
    result = derive_canonical_slug("length capped module slug")
    assert result is not None
    assert isinstance(result, str)
    assert len(result) <= 60


def test_slug_is_valid_identifier() -> None:
    """Returned slug must be a valid Python identifier."""
    result = derive_canonical_slug("some feature title here")
    assert result is not None
    assert result.isidentifier()


# ---------------------------------------------------------------------------
# Length cap
# ---------------------------------------------------------------------------


def test_long_title_slug_capped_at_60() -> None:
    """A 200-character feature title must produce a slug of at most 60 chars."""
    long_title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code "
        "and the retry counter has not yet reached the configured maximum"
    )
    result = derive_canonical_slug(long_title)
    assert result is not None
    assert len(result) <= 60


def test_slug_just_over_60_chars_capped() -> None:
    """A title whose full slug would be 61+ chars is capped to ≤60."""
    tok20 = "b" * 20
    title = f"{tok20} {tok20} {tok20}"  # full slug = 62 chars
    result = derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= 60


def test_short_title_unchanged() -> None:
    """A title whose slug is under 60 chars is returned unchanged (no truncation)."""
    title = "short title"
    result = derive_canonical_slug(title)
    full_slug = "short_title"
    assert result == full_slug


# ---------------------------------------------------------------------------
# Edge / boundary inputs
# ---------------------------------------------------------------------------


def test_empty_string_returns_none() -> None:
    result = derive_canonical_slug("")
    assert result is None


def test_whitespace_only_returns_none() -> None:
    result = derive_canonical_slug("   ")
    assert result is None


def test_none_input_returns_none() -> None:
    result = derive_canonical_slug(None)  # type: ignore[arg-type]
    assert result is None


def test_integer_input_returns_none() -> None:
    result = derive_canonical_slug(42)  # type: ignore[arg-type]
    assert result is None


def test_keyword_title_returns_none() -> None:
    result = derive_canonical_slug("class")
    assert result is None


def test_digit_only_title_returns_none() -> None:
    result = derive_canonical_slug("123")
    assert result is None


# ---------------------------------------------------------------------------
# build_fallback_criteria
# ---------------------------------------------------------------------------


def test_build_fallback_criteria_returns_list() -> None:
    criteria = build_fallback_criteria("slug limiter", "some description")
    assert isinstance(criteria, list)
    assert len(criteria) >= 3


def test_build_fallback_criteria_empty_name_raises() -> None:
    with pytest.raises(ValueError):
        build_fallback_criteria("", "description")


def test_build_fallback_criteria_whitespace_name_raises() -> None:
    with pytest.raises(ValueError):
        build_fallback_criteria("   ", "description")


def test_build_fallback_criteria_stopword_name_raises() -> None:
    with pytest.raises(ValueError):
        build_fallback_criteria("the a an for", "description")


def test_build_fallback_criteria_slug_under_255_bytes() -> None:
    """The File-exists AC path produced by build_fallback_criteria must be <255 bytes."""
    criteria = build_fallback_criteria("slug limiter module feature", "desc")
    file_exists = [c for c in criteria if c.startswith("File exists:")]
    assert file_exists, "Expected at least one 'File exists:' criterion"
    path = file_exists[0].split(":", 1)[1].strip()
    assert len(path.encode()) < 255, f"File path too long: {path!r}"
