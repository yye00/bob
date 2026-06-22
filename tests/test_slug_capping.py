"""Tests for bob3.slug_capping.derive_canonical_slug.

Verifies the length-capping invariant: no derived slug exceeds 60 characters,
preventing [Errno 36] File name too long when a feature title is very long.
"""

from __future__ import annotations

import pytest

from bob3.slug_capping import derive_canonical_slug


_MAX_SLUG_LEN = 60


# ── basic happy-path ──────────────────────────────────────────────────────────

def test_short_title_returns_slug() -> None:
    slug = derive_canonical_slug("fix login bug")
    assert slug is not None
    assert slug.isidentifier()
    assert len(slug) <= _MAX_SLUG_LEN


def test_slug_is_valid_python_identifier() -> None:
    slug = derive_canonical_slug("compute stability score")
    assert slug is not None
    assert slug.isidentifier()


def test_slug_is_lowercase() -> None:
    slug = derive_canonical_slug("Compute Stability Score")
    assert slug is not None
    assert slug == slug.lower()


# ── length-capping ────────────────────────────────────────────────────────────

def test_long_title_slug_capped_at_60() -> None:
    """A 200+ char title must yield a slug of at most 60 characters."""
    long_title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code that "
        "was rejected by the enhanced verifier on a transient failure"
    )
    slug = derive_canonical_slug(long_title)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN, (
        f"slug {slug!r} is {len(slug)} chars, expected ≤{_MAX_SLUG_LEN}"
    )


def test_slug_at_exactly_60_chars_unchanged() -> None:
    """A title whose full slug is ≤60 chars is returned unchanged."""
    # 4 tokens of 14 chars: 14+1+14+1+14+1+14 = 59 chars → under cap
    tok14 = "a" * 14
    title = f"{tok14} {tok14} {tok14} {tok14}"
    slug = derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN


def test_slug_just_over_60_chars_capped() -> None:
    """A title whose uncapped slug would exceed 60 chars is truncated."""
    tok20 = "b" * 20
    title = f"{tok20} {tok20} {tok20} {tok20}"
    slug = derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN


def test_single_very_long_token_capped() -> None:
    """A single token longer than 60 chars is hard-truncated."""
    title = "x" * 200
    slug = derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN
    assert slug.isidentifier()


# ── degenerate / None-returning inputs ───────────────────────────────────────

def test_empty_string_returns_none() -> None:
    assert derive_canonical_slug("") is None


def test_whitespace_only_returns_none() -> None:
    assert derive_canonical_slug("   \t\n  ") is None


def test_non_string_returns_none() -> None:
    assert derive_canonical_slug(None) is None  # type: ignore[arg-type]
    assert derive_canonical_slug(42) is None  # type: ignore[arg-type]
    assert derive_canonical_slug([]) is None  # type: ignore[arg-type]


def test_all_stopwords_returns_none() -> None:
    assert derive_canonical_slug("the a an for to of in on") is None


def test_python_keyword_returns_none() -> None:
    assert derive_canonical_slug("class") is None


def test_leading_digit_returns_none() -> None:
    assert derive_canonical_slug("123") is None


# ── capped slug is still a valid importable identifier ───────────────────────

def test_capped_slug_importable() -> None:
    """After capping, slug must be a valid Python identifier (importable)."""
    titles = [
        "very long feature title with many words that would exceed the limit",
        "F-R7-479 RCA auto-reset grant fresh attempt budget verification failure",
        "another extremely verbose title about some important infrastructure change",
    ]
    for title in titles:
        slug = derive_canonical_slug(title)
        if slug is not None:
            assert slug.isidentifier(), f"slug {slug!r} is not a valid identifier"
            assert len(slug) <= _MAX_SLUG_LEN


# ── integration: bob3.spec_synthesizer uses the same pipeline ─────────────────

def test_consistent_with_spec_synthesizer() -> None:
    """derive_canonical_slug agrees with spec_synthesizer._derive_canonical_slug."""
    from bob3.spec_synthesizer import _derive_canonical_slug as ss_derive

    titles = [
        "fix login bug",
        "compute stability score",
        "very long title " * 10,
        "",
        "the a an",
    ]
    for title in titles:
        assert derive_canonical_slug(title) == ss_derive(title), (
            f"Mismatch for title={title!r}"
        )
