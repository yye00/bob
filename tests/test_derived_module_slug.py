"""Tests for bob.derived_module_slug module.

Feature 2a18af78-0f2b-42cd-a6c5-3d916905a3b3

Verifies derive_canonical_slug and build_fallback_criteria functions
in the derived_module_slug module.
"""
from __future__ import annotations

import pytest

from bob.derived_module_slug import (
    build_fallback_criteria,
    cap_slug_length,
    derive_canonical_slug,
)


def test_derive_canonical_slug_long_title_capped() -> None:
    """Core feature: long title produces slug ≤60 chars."""
    long_title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code "
        "not just infra transient currently only infra reclassification "
        "reopens the budget so legitimate verification failures NH at "
        "attempt 3 with unused budget"
    )
    slug = derive_canonical_slug(long_title)
    assert slug is not None, "Expected a slug, got None"
    assert len(slug) <= 60, f"Slug exceeds 60 chars: {len(slug)} — {slug!r}"
    assert slug.isidentifier(), f"Not a valid Python identifier: {slug!r}"


def test_derive_canonical_slug_short_title_unchanged() -> None:
    """A title that already slugs under 60 chars is returned intact."""
    title = "simple alpha beta gamma"
    slug = derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= 60
    assert "alpha" in slug
    assert "beta" in slug


def test_derive_canonical_slug_whole_token_boundaries() -> None:
    """Slug is capped on whole-token boundaries — no mid-word truncation."""
    # Four 15-char tokens; together (63 chars) exceed the 60-char cap.
    title = "aaaaaaaaaaaaaaa bbbbbbbbbbbbbbb ccccccccccccccc ddddddddddddddd"
    slug = derive_canonical_slug(title)
    assert slug is not None
    parts = slug.split("_")
    for part in parts:
        assert part in {
            "aaaaaaaaaaaaaaa",
            "bbbbbbbbbbbbbbb",
            "ccccccccccccccc",
        }, f"Unexpected partial token in slug: {part!r}"


def test_derive_canonical_slug_single_long_token_truncated() -> None:
    """A single token longer than 60 chars is hard-truncated to the cap."""
    title = "a" * 100
    slug = derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= 60


def test_derive_canonical_slug_is_deterministic() -> None:
    """Calling derive_canonical_slug twice returns the same slug."""
    title = "some feature with moderate length title words"
    assert derive_canonical_slug(title) == derive_canonical_slug(title)


def test_derive_canonical_slug_is_valid_identifier() -> None:
    """Result is always a valid Python identifier."""
    title = (
        "very long feature about orchestrator dispatch concurrency "
        "and readiness derivation"
    )
    slug = derive_canonical_slug(title)
    assert slug is not None
    assert slug.isidentifier()


def test_derive_canonical_slug_empty_returns_none() -> None:
    """Empty or whitespace-only titles yield None."""
    assert derive_canonical_slug("") is None
    assert derive_canonical_slug("   ") is None


def test_derive_canonical_slug_non_string_returns_none() -> None:
    """Non-string input yields None."""
    assert derive_canonical_slug(None) is None  # type: ignore[arg-type]
    assert derive_canonical_slug(123) is None  # type: ignore[arg-type]


def test_build_fallback_criteria_returns_list() -> None:
    """build_fallback_criteria returns a non-empty list of strings."""
    criteria = build_fallback_criteria("my feature alpha", "does something useful")
    assert isinstance(criteria, list)
    assert len(criteria) >= 3
    for c in criteria:
        assert isinstance(c, str)


def test_build_fallback_criteria_file_and_function_same_slug() -> None:
    """File-exists and Function-defined ACs use the same slug."""
    criteria = build_fallback_criteria("my feature alpha", "does something useful")
    file_acs = [c for c in criteria if c.startswith("File exists:")]
    func_acs = [c for c in criteria if c.startswith("Function defined:")]
    assert file_acs, "Expected at least one File exists AC"
    assert func_acs, "Expected at least one Function defined AC"
    # Extract slug from File exists: src/bob/<slug>.py
    file_slug = file_acs[0].replace("File exists: src/bob/", "").replace(".py", "")
    # Extract slug from Function defined: bob.<slug>.<something>
    func_parts = func_acs[0].replace("Function defined: bob.", "").split(".")
    func_module_slug = func_parts[0]
    assert file_slug == func_module_slug, (
        f"File slug {file_slug!r} != function module slug {func_module_slug!r}"
    )


def test_build_fallback_criteria_long_title_slug_capped() -> None:
    """build_fallback_criteria caps slug in file/function ACs for long titles."""
    long_title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code "
        "not just infra transient"
    )
    criteria = build_fallback_criteria(long_title, "some description")
    file_acs = [c for c in criteria if c.startswith("File exists:")]
    assert file_acs, "Expected at least one File exists AC"
    file_slug = file_acs[0].replace("File exists: src/bob/", "").replace(".py", "")
    assert len(file_slug) <= 60, (
        f"Slug in File exists AC exceeds 60 chars: {len(file_slug)} — {file_slug!r}"
    )
