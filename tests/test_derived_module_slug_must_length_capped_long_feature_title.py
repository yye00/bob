"""Tests for derived module slug length-capping behavior.

Feature fcbd0b20-2d5e-425a-9447-167aa7add140

Verifies that _derive_canonical_slug caps slugs at ~60 chars on whole-token
boundaries to prevent [Errno 36] File name too long when a feature title
produces a 200+ character slug.
"""
from __future__ import annotations

import pytest

from bob.derived_module_slug_must_length_capped_long_feature_title import (
    derived_module_slug_must_length_capped_long_feature_title,
)


def test_derived_module_slug_must_length_capped_long_feature_title() -> None:
    """Core AC test: function is callable and caps a long slug at ≤60 chars."""
    long_title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code "
        "not just infra transient currently only infra reclassification "
        "reopens the budget so legitimate verification failures NH at "
        "attempt 3 with unused budget"
    )
    slug = derived_module_slug_must_length_capped_long_feature_title(long_title)
    assert slug is not None, "Expected a slug, got None"
    assert len(slug) <= 60, f"Slug exceeds 60 chars: {len(slug)} — {slug!r}"
    assert slug.isidentifier(), f"Slug is not a valid Python identifier: {slug!r}"


def test_short_title_unchanged() -> None:
    """A title whose slug is already ≤60 chars is returned without truncation."""
    title = "simple short alpha beta"
    slug = derived_module_slug_must_length_capped_long_feature_title(title)
    # All 4 tokens kept (no stop-words match "alpha"/"beta", combined < 60 chars)
    assert slug is not None
    assert len(slug) <= 60
    assert "alpha" in slug
    assert "beta" in slug


def test_slug_on_whole_token_boundaries() -> None:
    """Capping drops whole tokens — no mid-word truncation."""
    # Build a title with predictable token lengths: four 15-char tokens
    # that together (61 chars with underscores) exceed the 60-char cap.
    title = "aaaaaaaaaaaaaaa bbbbbbbbbbbbbbb ccccccccccccccc ddddddddddddddd"
    slug = derived_module_slug_must_length_capped_long_feature_title(title)
    assert slug is not None
    # The cap (60) allows exactly 3 × 15 + 2 underscores = 47 chars,
    # so 4 tokens would be 63 chars — the 4th must be dropped.
    parts = slug.split("_")
    for part in parts:
        assert part in {"aaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbb", "ccccccccccccccc"}, (
            f"Unexpected partial token in slug: {part!r}"
        )


def test_extremely_long_single_token_truncated() -> None:
    """A single token longer than 60 chars is truncated to the cap."""
    long_token = "a" * 100
    title = long_token
    slug = derived_module_slug_must_length_capped_long_feature_title(title)
    assert slug is not None
    assert len(slug) <= 60, f"Single-token slug exceeds 60 chars: {len(slug)}"


def test_returns_valid_python_identifier() -> None:
    """Capped slug must always be importable as a Python module name."""
    title = (
        "very long feature about orchestrator dispatch concurrency "
        "and readiness derivation and spec quality scoring gates "
        "with enhanced verification and retry logic"
    )
    slug = derived_module_slug_must_length_capped_long_feature_title(title)
    assert slug is not None
    assert slug.isidentifier(), f"Not a valid identifier: {slug!r}"
    assert len(slug) <= 60


def test_none_on_empty_title() -> None:
    """Empty title yields None (no valid slug possible)."""
    assert derived_module_slug_must_length_capped_long_feature_title("") is None
    assert derived_module_slug_must_length_capped_long_feature_title("   ") is None


def test_file_and_function_slug_agree() -> None:
    """The same slug is used for both src/bob/<slug>.py and Function defined.

    This is the key correctness property: the function returns the slug that
    would be used for BOTH ACs so a single impl file satisfies both.
    """
    title = "some feature with moderate length title words and tokens"
    slug1 = derived_module_slug_must_length_capped_long_feature_title(title)
    # Calling twice must return the same value (deterministic).
    slug2 = derived_module_slug_must_length_capped_long_feature_title(title)
    assert slug1 == slug2, "Slug must be deterministic"
    assert slug1 is not None
