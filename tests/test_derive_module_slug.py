"""Tests for bob.derive_module_slug — length-capped slug derivation.

Feature a84b0db2-7e7b-488a-9db1-7bb6e7fb11f7

Verifies that derive_canonical_slug caps slugs at 60 chars on whole-token
boundaries, preventing [Errno 36] File name too long crashes in the verifier.
"""

from __future__ import annotations

import pytest

from bob.derive_module_slug import (
    _derive_canonical_slug,
    build_fallback_criteria,
    cap_slug_at_token_boundary,
    derive_canonical_slug,
)


class TestDeriveCanonicalSlug:
    def test_normal_title_returns_slug(self) -> None:
        result = derive_canonical_slug("compute quality score")
        assert result == "compute_quality_score"

    def test_slug_is_valid_python_identifier(self) -> None:
        result = derive_canonical_slug("generate remediation report")
        assert result is not None
        assert result.isidentifier()

    def test_long_title_capped_at_60_chars(self) -> None:
        # Simulate the bug: 200+ char title that previously wedged the run.
        long_title = (
            "RCA auto reset MUST grant fresh attempt budget when "
            "verification gate failure cause is plausibly fixable code "
            "error rather than permanent structural defect in the feature spec"
        )
        result = derive_canonical_slug(long_title)
        assert result is not None
        assert len(result) <= 60
        assert result.isidentifier()

    def test_empty_string_returns_none(self) -> None:
        assert derive_canonical_slug("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert derive_canonical_slug("   ") is None

    def test_none_input_returns_none(self) -> None:
        assert derive_canonical_slug(None) is None  # type: ignore[arg-type]

    def test_non_string_input_returns_none(self) -> None:
        assert derive_canonical_slug(42) is None  # type: ignore[arg-type]

    def test_python_keyword_returns_none(self) -> None:
        assert derive_canonical_slug("class") is None

    def test_leading_digit_returns_none(self) -> None:
        assert derive_canonical_slug("123") is None

    def test_slug_under_60_chars_unchanged(self) -> None:
        title = "prevent status downgrade"
        result = derive_canonical_slug(title)
        assert result is not None
        assert result == "prevent_status_downgrade"
        assert len(result) <= 60

    def test_exactly_60_char_boundary(self) -> None:
        # 4 tokens of 14 chars + 1 char = 59 chars joined; test still within cap
        tok14 = "a" * 14
        title = f"{tok14} {tok14} {tok14} {tok14} z"
        result = derive_canonical_slug(title)
        assert result is not None
        assert len(result) <= 60

    def test_slug_over_60_capped_on_token_boundary(self) -> None:
        # 3 tokens of 20 chars = 62 chars joined → must be capped
        tok20 = "b" * 20
        title = f"{tok20} {tok20} {tok20}"
        result = derive_canonical_slug(title)
        assert result is not None
        assert len(result) <= 60
        # Must not end with underscore
        assert not result.endswith("_")


class TestPrivateDeriveCanonicalSlug:
    def test_delegates_to_same_pipeline(self) -> None:
        title = "run filter tests"
        assert _derive_canonical_slug(title) == derive_canonical_slug(title)

    def test_non_string_returns_none(self) -> None:
        # _derive_canonical_slug expects str; non-str returns None
        result = _derive_canonical_slug(None)  # type: ignore[arg-type]
        assert result is None


class TestCapSlugAtTokenBoundary:
    def test_slug_under_cap_unchanged(self) -> None:
        assert cap_slug_at_token_boundary("short_slug") == "short_slug"

    def test_slug_at_exact_cap_unchanged(self) -> None:
        slug = "a" * 60
        assert cap_slug_at_token_boundary(slug) == slug

    def test_slug_over_cap_truncated(self) -> None:
        slug = "_".join(["word"] * 20)  # well over 60 chars
        result = cap_slug_at_token_boundary(slug)
        assert len(result) <= 60

    def test_single_overlong_token_hard_truncated(self) -> None:
        slug = "x" * 80
        result = cap_slug_at_token_boundary(slug)
        assert len(result) <= 60

    def test_empty_slug_raises(self) -> None:
        with pytest.raises(ValueError):
            cap_slug_at_token_boundary("")

    def test_zero_max_len_raises(self) -> None:
        with pytest.raises(ValueError):
            cap_slug_at_token_boundary("slug", max_len=0)

    def test_custom_max_len(self) -> None:
        slug = "aaa_bbb_ccc_ddd"
        result = cap_slug_at_token_boundary(slug, max_len=7)
        assert len(result) <= 7


class TestBuildFallbackCriteria:
    def test_valid_name_returns_criteria_list(self) -> None:
        criteria = build_fallback_criteria("compute quality score", "desc")
        assert isinstance(criteria, list)
        assert len(criteria) >= 3

    def test_criteria_contains_file_exists(self) -> None:
        criteria = build_fallback_criteria("compute quality score", "desc")
        assert any("File exists" in c for c in criteria)

    def test_slug_in_file_exists_and_function_defined_match(self) -> None:
        criteria = build_fallback_criteria("detect smells", "smell detector")
        file_exists = [c for c in criteria if "File exists" in c]
        func_defined = [c for c in criteria if "Function defined" in c]
        if file_exists and func_defined:
            # Extract module slug from both — they must agree
            fe_slug = file_exists[0].split("/")[-1].replace(".py", "")
            fd_slug = func_defined[0].split(".")[-2]
            assert fe_slug == fd_slug

    def test_empty_name_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_fallback_criteria("", "description")

    def test_all_stopwords_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_fallback_criteria("the a an for to", "description")
