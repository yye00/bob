"""Tests for bob3.slug_cap — length-capped module slug derivation.

Feature 3ae452ae-fa7e-4ed8-9028-59e1cb8dd420

Verifies that derive_canonical_slug in bob3.slug_cap caps slugs at 60
characters on whole-token boundaries and correctly handles edge cases.
"""

from __future__ import annotations

import pytest

from bob3.slug_cap import build_fallback_criteria, derive_canonical_slug


def test_short_title_unchanged() -> None:
    """A title with a short slug is returned unchanged."""
    result = derive_canonical_slug("rca auto reset")
    assert result is not None
    assert result == "rca_auto_reset"
    assert len(result) <= 60


def test_long_title_capped_at_60() -> None:
    """A very long title produces a slug capped at ≤60 characters."""
    long_title = " ".join(["word"] * 30)
    result = derive_canonical_slug(long_title)
    assert result is not None
    assert len(result) <= 60
    assert result.isidentifier()


def test_exactly_60_char_slug_unchanged() -> None:
    """A title whose slug is exactly 60 chars is returned as-is."""
    tok14 = "a" * 14
    title = f"{tok14} {tok14} {tok14} {tok14} z"
    result = derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= 60


def test_slug_over_60_chars_capped() -> None:
    """A title whose full slug exceeds 60 chars is capped to ≤60."""
    tok20 = "b" * 20
    title = f"{tok20} {tok20} {tok20}"
    result = derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= 60


def test_none_returns_none() -> None:
    """None input returns None, does not raise."""
    assert derive_canonical_slug(None) is None  # type: ignore[arg-type]


def test_empty_string_returns_none() -> None:
    """Empty string returns None, does not raise."""
    assert derive_canonical_slug("") is None


def test_whitespace_only_returns_none() -> None:
    """Whitespace-only string returns None."""
    assert derive_canonical_slug("   ") is None


def test_integer_returns_none() -> None:
    """Non-string input returns None."""
    assert derive_canonical_slug(42) is None  # type: ignore[arg-type]


def test_slug_is_valid_python_identifier() -> None:
    """Result (when not None) is always a valid Python identifier."""
    titles = [
        "rca auto reset",
        "classification pipeline",
        "spec synthesizer slug capping fix",
    ]
    for title in titles:
        result = derive_canonical_slug(title)
        if result is not None:
            assert result.isidentifier(), f"Not an identifier: {result!r}"


def test_slug_uses_underscores_not_hyphens() -> None:
    """Slug uses underscores as word separators."""
    result = derive_canonical_slug("feature name test")
    assert result is not None
    assert "-" not in result
    assert "_" in result or len(result.split()) == 1


def test_keyword_title_returns_none() -> None:
    """A title that reduces to a Python keyword returns None."""
    assert derive_canonical_slug("class") is None


def test_build_fallback_criteria_valid_input() -> None:
    """Valid input returns a non-empty criteria list."""
    criteria = build_fallback_criteria("rca auto reset", "some description")
    assert isinstance(criteria, list)
    assert len(criteria) >= 3


def test_build_fallback_criteria_slug_length_capped() -> None:
    """Fallback criteria file-exists AC uses a capped slug."""
    long_name = " ".join(["word"] * 30)
    criteria = build_fallback_criteria(long_name, "description")
    file_exists_acs = [c for c in criteria if c.startswith("File exists:")]
    assert file_exists_acs, "Expected at least one File exists: AC"
    for ac in file_exists_acs:
        # Extract the filename from the AC
        path = ac.split("File exists:")[-1].strip()
        filename = path.split("/")[-1]
        assert len(filename) <= 64, (
            f"Filename too long ({len(filename)}): {filename!r}"
        )


def test_build_fallback_criteria_empty_name_raises() -> None:
    """Empty feature name raises ValueError."""
    with pytest.raises(ValueError):
        build_fallback_criteria("", "some description")


def test_integration_with_spec_synthesizer() -> None:
    """derive_canonical_slug delegates to spec_synthesizer correctly."""
    from bob3.spec_synthesizer import _derive_canonical_slug as ss_fn

    title = "automated rca reset pipeline"
    assert derive_canonical_slug(title) == ss_fn(title)
