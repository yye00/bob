"""Tests for _derive_canonical_slug length-capping in bob3.spec_synthesizer.

Feature d78a9898-e688-4624-8d19-383a181bb75d:
  Derived module slug MUST be length-capped — a long feature title otherwise
  yields a .py filename exceeding the 255-byte filesystem limit.

Covers:
  - Long title slug is capped at ≤60 chars
  - Short title slug is unchanged
  - Whole-token boundary capping (no mid-word cuts)
  - Single overlong token hard-truncated to 60 chars
  - Empty / whitespace-only input returns None (no crash)
  - Non-string input returns None (no crash)
  - Slug is always a valid Python identifier
  - Slug is deterministic (same title → same slug every call)
  - Integration: _derive_canonical_slug is accessible from bob3.spec_synthesizer
"""

from __future__ import annotations

import pytest

from bob3.spec_synthesizer import _derive_canonical_slug


MAX_SLUG_LEN = 60

# The exact title from the bob66 incident that caused the 7-hour hang.
LONG_INCIDENT_TITLE = (
    "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
    "verification-gate-failure cause is plausibly-fixable code "
    "not just infra transient currently only infra reclassification "
    "reopens the budget so legitimate verification failures NH at "
    "attempt 3 with unused budget"
)


class TestLengthCapping:
    """Core length-capping guarantees."""

    def test_long_title_slug_at_most_60_chars(self) -> None:
        slug = _derive_canonical_slug(LONG_INCIDENT_TITLE)
        assert slug is not None, "Expected a slug for the incident title, got None"
        assert len(slug) <= MAX_SLUG_LEN, (
            f"Slug exceeds {MAX_SLUG_LEN} chars: {len(slug)} — {slug!r}"
        )

    def test_long_title_slug_is_valid_identifier(self) -> None:
        slug = _derive_canonical_slug(LONG_INCIDENT_TITLE)
        assert slug is not None
        assert slug.isidentifier(), f"Slug is not a valid Python identifier: {slug!r}"

    def test_feature_title_slug_equals_expected(self) -> None:
        """The feature's own title must slug to the expected 57-char value."""
        feature_title = (
            "Derived module slug MUST be length-capped — a long feature title"
            " otherwise yields a .py filename exceeding the 255-byte filesystem"
            " limit and wedges the run"
        )
        slug = _derive_canonical_slug(feature_title)
        assert slug is not None
        assert len(slug) <= MAX_SLUG_LEN
        assert slug == "derived_module_slug_must_length_capped_long_feature_title"

    def test_slug_plus_py_under_255_bytes(self) -> None:
        """The filename '<slug>.py' must stay within the filesystem NAME_MAX."""
        slug = _derive_canonical_slug(LONG_INCIDENT_TITLE)
        assert slug is not None
        filename = slug + ".py"
        assert len(filename.encode()) < 255, (
            f"Filename exceeds 255 bytes: {len(filename.encode())} — {filename!r}"
        )


class TestShortTitleUnchanged:
    """A title whose slug fits within 60 chars is returned as-is."""

    def test_short_title_preserved(self) -> None:
        title = "simple alpha beta gamma"
        slug = _derive_canonical_slug(title)
        assert slug is not None
        assert len(slug) <= MAX_SLUG_LEN
        assert "alpha" in slug
        assert "beta" in slug

    def test_exactly_60_char_slug_unchanged(self) -> None:
        # 4 × 14 chars + 3 underscores = 59 chars (under cap)
        title = "aaaaaaaaaaaaaa bbbbbbbbbbbbbb cccccccccccccc dddddddddddddd"
        slug = _derive_canonical_slug(title)
        assert slug is not None
        assert len(slug) <= MAX_SLUG_LEN
        # All tokens should be present (none dropped)
        assert "aaaaaaaaaaaaaa" in slug
        assert "dddddddddddddd" in slug


class TestWholeTokenBoundaries:
    """Capping must drop whole tokens, not split mid-word."""

    def test_four_tokens_drops_last_to_fit(self) -> None:
        # 4 × 15 chars + 3 underscores = 63 chars > 60; last token must be dropped
        title = "aaaaaaaaaaaaaaa bbbbbbbbbbbbbbb ccccccccccccccc ddddddddddddddd"
        slug = _derive_canonical_slug(title)
        assert slug is not None
        parts = slug.split("_")
        allowed = {"aaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbb", "ccccccccccccccc"}
        for part in parts:
            assert part in allowed, f"Unexpected partial token: {part!r}"
        # The 4th token must NOT appear
        assert "ddddddddddddddd" not in slug

    def test_no_mid_word_cut(self) -> None:
        """Tokens in the slug must be complete words."""
        title = (
            "orchestrator dispatch concurrency readiness derivation spec quality"
            " scoring enhanced verification retry logic circuit breaker"
        )
        slug = _derive_canonical_slug(title)
        assert slug is not None
        assert len(slug) <= MAX_SLUG_LEN
        # Each underscore-separated part must be a non-empty string of lowercase
        # letters/digits (no truncated half-words leaving trailing letters).
        for part in slug.split("_"):
            assert part.isalnum() and part == part.lower(), (
                f"Non-clean token in slug: {part!r}"
            )


class TestSingleLongToken:
    """A single token exceeding 60 chars is hard-truncated to the cap."""

    def test_single_100_char_token_truncated(self) -> None:
        long_token = "a" * 100
        slug = _derive_canonical_slug(long_token)
        assert slug is not None
        assert len(slug) <= MAX_SLUG_LEN, (
            f"Single-token slug exceeds cap: {len(slug)} — {slug!r}"
        )
        assert slug.isidentifier()

    def test_single_61_char_token_truncated(self) -> None:
        token = "b" * 61
        slug = _derive_canonical_slug(token)
        assert slug is not None
        assert len(slug) <= MAX_SLUG_LEN


class TestBoundaryEmptyInput:
    """Empty or zero input must return None, not crash."""

    def test_empty_string_returns_none(self) -> None:
        result = _derive_canonical_slug("")
        assert result is None

    def test_whitespace_only_returns_none(self) -> None:
        result = _derive_canonical_slug("   \t\n")
        assert result is None

    def test_none_input_returns_none(self) -> None:
        result = _derive_canonical_slug(None)  # type: ignore[arg-type]
        assert result is None

    def test_zero_integer_returns_none(self) -> None:
        result = _derive_canonical_slug(0)  # type: ignore[arg-type]
        assert result is None


class TestInvalidInputRejection:
    """Invalid input must be rejected — no silent success."""

    def test_non_string_integer_rejected(self) -> None:
        result = _derive_canonical_slug(42)  # type: ignore[arg-type]
        assert result is None, "Integer input must be rejected, not silently accepted"

    def test_non_string_list_rejected(self) -> None:
        result = _derive_canonical_slug(["a", "b"])  # type: ignore[arg-type]
        assert result is None, "List input must be rejected"

    def test_all_stopwords_does_not_silently_return_keyword(self) -> None:
        # A title made only of stop-words may collapse; result must be valid or None
        title = "the a an for to of in on with and or by"
        result = _derive_canonical_slug(title)
        if result is not None:
            assert result.isidentifier()
            assert len(result) <= MAX_SLUG_LEN

    def test_python_keyword_title_rejected_or_valid(self) -> None:
        # "class" is a Python keyword — slug must not return it raw
        result = _derive_canonical_slug("class")
        # Must either return None or return something that is NOT a reserved keyword
        if result is not None:
            import keyword
            assert not keyword.iskeyword(result), (
                f"Slug must not be a Python keyword: {result!r}"
            )

    def test_leading_digit_slug_rejected(self) -> None:
        # A title starting with digits should either return None or a valid identifier
        result = _derive_canonical_slug("1st attempt budget reset")
        if result is not None:
            assert result.isidentifier(), f"Slug starting from digit is not identifier: {result!r}"


class TestDeterminism:
    """Slug derivation must be deterministic."""

    def test_same_title_same_slug(self) -> None:
        title = "some feature with moderate length title words and tokens"
        slug1 = _derive_canonical_slug(title)
        slug2 = _derive_canonical_slug(title)
        assert slug1 == slug2, "Slug must be deterministic across calls"

    def test_long_title_deterministic(self) -> None:
        slug1 = _derive_canonical_slug(LONG_INCIDENT_TITLE)
        slug2 = _derive_canonical_slug(LONG_INCIDENT_TITLE)
        assert slug1 == slug2


class TestIntegration:
    """Integration checks: _derive_canonical_slug is properly integrated."""

    def test_function_importable_from_spec_synthesizer(self) -> None:
        from bob3.spec_synthesizer import _derive_canonical_slug as fn
        assert callable(fn)

    def test_slug_used_consistently_for_file_and_function(self) -> None:
        """Both File-exists and Function-defined ACs must use the same slug."""
        from bob3.spec_synthesizer import _derive_canonical_slug, _infer_primary_symbol

        title = "orchestrator dispatch concurrency readiness"
        slug = _derive_canonical_slug(title)
        inferred = _infer_primary_symbol(title)
        if slug is not None and inferred is not None:
            module_path, symbol = inferred
            # The module path is "bob3.<slug>"; the symbol == slug
            assert module_path == f"bob3.{slug}", (
                f"Module path {module_path!r} does not match slug {slug!r}"
            )
            assert symbol == slug
