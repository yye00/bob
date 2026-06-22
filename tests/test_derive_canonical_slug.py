"""Tests for bob3._derive_canonical_slug length-capping behavior.

Feature 8b7c1581-e40b-4223-99ba-67cea2f68f15

Verifies that _derive_canonical_slug caps slugs at ≤60 chars on whole-token
boundaries, preventing [Errno 36] File name too long when a feature title
produces a 200+ character slug (the bob66 7-hour hang incident).
"""

from __future__ import annotations

import pytest

from bob3.spec_synthesizer import _derive_canonical_slug
from bob3.test_slug_capping import verify_slug_capping, slug_is_capped

_MAX_SLUG_LEN = 60


class TestDeriveCanonicaSlugLengthCap:
    """Core length-capping invariant tests."""

    def test_long_title_capped_at_60_chars(self) -> None:
        """The bob66 incident title must produce a slug ≤60 chars."""
        long_title = (
            "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
            "verification-gate-failure cause is plausibly-fixable code "
            "not just infra transient currently only infra reclassification "
            "reopens the budget so legitimate verification failures NH at "
            "attempt 3 with unused budget"
        )
        slug = _derive_canonical_slug(long_title)
        assert slug is not None, "Expected a slug, got None"
        assert len(slug) <= _MAX_SLUG_LEN, (
            f"Slug exceeds {_MAX_SLUG_LEN} chars: {len(slug)} — {slug!r}"
        )

    def test_short_title_unchanged(self) -> None:
        """A title whose slug is already ≤60 chars is returned without truncation."""
        title = "alpha beta gamma delta"
        slug = _derive_canonical_slug(title)
        assert slug is not None
        assert len(slug) <= _MAX_SLUG_LEN
        assert "alpha" in slug
        assert "beta" in slug

    def test_slug_on_whole_token_boundaries(self) -> None:
        """Capping drops whole tokens — no mid-word truncation."""
        # 4 tokens of 15 chars each: joined = 63 chars (exceeds 60)
        title = "aaaaaaaaaaaaaaa bbbbbbbbbbbbbbb ccccccccccccccc ddddddddddddddd"
        slug = _derive_canonical_slug(title)
        assert slug is not None
        parts = slug.split("_")
        valid_tokens = {"aaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbb", "ccccccccccccccc"}
        for part in parts:
            assert part in valid_tokens, f"Unexpected partial token in slug: {part!r}"

    def test_extremely_long_single_token_handled(self) -> None:
        """A single token longer than 60 chars does not raise; result is valid."""
        long_token = "x" * 200
        slug = _derive_canonical_slug(long_token)
        # Either None (rejected) or a slug ≤60 chars — must not crash
        if slug is not None:
            assert len(slug) <= _MAX_SLUG_LEN

    def test_slug_is_valid_python_identifier(self) -> None:
        """Capped slug must always be importable as a Python module name."""
        title = (
            "orchestrator dispatch concurrency readiness derivation spec "
            "quality scoring gates enhanced verification retry logic budget"
        )
        slug = _derive_canonical_slug(title)
        assert slug is not None
        assert slug.isidentifier(), f"Not a valid identifier: {slug!r}"
        assert len(slug) <= _MAX_SLUG_LEN

    def test_slug_is_deterministic(self) -> None:
        """Same title always produces the same slug."""
        title = "some feature with moderate length title words and tokens"
        slug1 = _derive_canonical_slug(title)
        slug2 = _derive_canonical_slug(title)
        assert slug1 == slug2, "Slug must be deterministic"


class TestDeriveCanonicaSlugEmptyAndInvalidInput:
    """Boundary: empty and invalid inputs must not crash."""

    def test_empty_string_returns_none(self) -> None:
        """Empty title returns None — not a crash."""
        assert _derive_canonical_slug("") is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only title returns None — not a crash."""
        assert _derive_canonical_slug("   ") is None
        assert _derive_canonical_slug("\t\n") is None

    def test_non_string_returns_none(self) -> None:
        """Non-string input returns None — not a crash."""
        assert _derive_canonical_slug(None) is None  # type: ignore[arg-type]
        assert _derive_canonical_slug(42) is None  # type: ignore[arg-type]
        assert _derive_canonical_slug([]) is None  # type: ignore[arg-type]

    def test_all_stopwords_does_not_crash(self) -> None:
        """A title of all stop-words returns None or a best-effort slug."""
        # "the and or but" — all stop-words. Must not raise, just return None or slug.
        result = _derive_canonical_slug("the and or but")
        # Either None (no usable tokens) or a valid slug — never an exception.
        if result is not None:
            assert result.isidentifier()
            assert len(result) <= _MAX_SLUG_LEN

    def test_unicode_title_does_not_crash(self) -> None:
        """Unicode titles are NFKD-folded and must not crash."""
        slug = _derive_canonical_slug("café résumé naïve")
        if slug is not None:
            assert slug.isidentifier()
            assert len(slug) <= _MAX_SLUG_LEN


class TestVerifySlugCappingModule:
    """Tests for the test_slug_capping module's verify_slug_capping function."""

    def test_verify_raises_for_empty_input(self) -> None:
        """verify_slug_capping raises ValueError for empty string."""
        with pytest.raises(ValueError, match="invalid input"):
            verify_slug_capping("")

    def test_verify_raises_for_whitespace(self) -> None:
        """verify_slug_capping raises ValueError for whitespace-only input."""
        with pytest.raises(ValueError, match="invalid input"):
            verify_slug_capping("   ")

    def test_verify_raises_for_non_string(self) -> None:
        """verify_slug_capping raises ValueError for non-string input."""
        with pytest.raises(ValueError, match="invalid input"):
            verify_slug_capping(None)  # type: ignore[arg-type]

    def test_verify_returns_capped_slug(self) -> None:
        """verify_slug_capping returns a valid capped slug for a long title."""
        long_title = (
            "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
            "verification-gate-failure cause is plausibly-fixable code "
            "not just infra transient currently only infra reclassification"
        )
        slug = verify_slug_capping(long_title)
        assert slug is not None
        assert slug.isidentifier()
        assert len(slug) <= _MAX_SLUG_LEN

    def test_slug_is_capped_returns_true_for_long_title(self) -> None:
        """slug_is_capped returns True when the derived slug satisfies invariant."""
        long_title = (
            "orchestrator liveness probe must exclude ancestry shell wrappers "
            "verification gate failure cause plausibly fixable code"
        )
        assert slug_is_capped(long_title) is True

    def test_slug_is_capped_returns_false_for_empty(self) -> None:
        """slug_is_capped returns False for empty input (no slug possible)."""
        assert slug_is_capped("") is False
        assert slug_is_capped("   ") is False


class TestIntegrationWithSpecSynthesizer:
    """Integration: _derive_canonical_slug is wired into spec_synthesizer."""

    def test_build_fallback_criteria_raises_for_empty_title(self) -> None:
        """_build_fallback_criteria raises ValueError for an empty title."""
        from bob3.spec_synthesizer import _build_fallback_criteria

        with pytest.raises(ValueError):
            _build_fallback_criteria("", "")

    def test_build_fallback_criteria_produces_capped_slug(self) -> None:
        """_build_fallback_criteria uses the same capped slug for file and function."""
        from bob3.spec_synthesizer import _build_fallback_criteria

        long_title = (
            "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
            "verification-gate-failure cause is plausibly-fixable code "
            "not just infra transient reclassification reopens the budget"
        )
        criteria = _build_fallback_criteria(long_title, "description")
        file_criteria = [c for c in criteria if c.startswith("File exists:")]
        func_criteria = [c for c in criteria if c.startswith("Function defined:")]
        assert file_criteria, "No 'File exists:' criterion emitted"
        assert func_criteria, "No 'Function defined:' criterion emitted"

        # Extract slug from each
        file_slug = file_criteria[0].split("src/bob3/")[1].removesuffix(".py")
        func_slug = func_criteria[0].split("bob3.")[1].split(".")[0]
        assert file_slug == func_slug, (
            f"File slug {file_slug!r} != function slug {func_slug!r}"
        )
        assert len(file_slug) <= _MAX_SLUG_LEN

    def test_slugify_delegates_to_derive_canonical_slug(self) -> None:
        """_slugify agrees with _derive_canonical_slug for the same title."""
        from bob3.spec_synthesizer import _slugify

        title = "orchestrator liveness probe ancestry exclusion"
        slug_direct = _derive_canonical_slug(title)
        slug_via_slugify = _slugify(title)
        assert slug_direct == slug_via_slugify or slug_via_slugify == "feature"
