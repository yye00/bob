"""Tests for dark_factory.boundary_error_coverage.

Verifies that ensure_boundary_and_error_coverage and get_prose_acs use
word-boundary regexes on prose ACs only — preventing naive slug-substring
false positives that caused 32/118 features to score 0.0 on the composite
spec_quality gate.
"""

from __future__ import annotations

import pytest
from dark_factory.boundary_error_coverage import (
    ensure_boundary_and_error_coverage,
    get_prose_acs,
)


# ---------------------------------------------------------------------------
# get_prose_acs — filtering tests
# ---------------------------------------------------------------------------


class TestGetProseAcs:
    def test_empty_list(self):
        assert get_prose_acs([]) == []

    def test_returns_prose_ac(self):
        result = get_prose_acs(["The function handles normal input."])
        assert result == ["The function handles normal input."]

    def test_filters_file_exists(self):
        result = get_prose_acs(["File exists: src/foo.py"])
        assert result == []

    def test_filters_function_defined(self):
        result = get_prose_acs(["Function defined: bob3.foo.bar"])
        assert result == []

    def test_filters_pytest(self):
        result = get_prose_acs(["pytest: tests/test_foo.py"])
        assert result == []

    def test_filters_integration(self):
        result = get_prose_acs(["integration: bob3.memory"])
        assert result == []

    def test_filters_class_defined(self):
        result = get_prose_acs(["Class defined: bob3.foo.MyClass"])
        assert result == []

    def test_filters_field_exists(self):
        result = get_prose_acs(["field exists: some_field"])
        assert result == []

    def test_filters_file_modified(self):
        result = get_prose_acs(["file modified: src/bob3/foo.py"])
        assert result == []

    def test_filters_ci_tests(self):
        result = get_prose_acs(["ci tests: run_all"])
        assert result == []

    def test_keeps_behavior_ac(self):
        result = get_prose_acs(["behavior: when empty input is given, return empty list"])
        assert result == ["behavior: when empty input is given, return empty list"]

    def test_mixed_structural_and_prose(self):
        criteria = [
            "File exists: src/foo.py",
            "The function must handle empty lists.",
            "pytest: tests/test_foo.py",
            "Must raise ValueError for None input.",
        ]
        result = get_prose_acs(criteria)
        assert result == [
            "The function must handle empty lists.",
            "Must raise ValueError for None input.",
        ]

    def test_preserves_order(self):
        criteria = ["prose one", "File exists: x", "prose two", "pytest: y", "prose three"]
        result = get_prose_acs(criteria)
        assert result == ["prose one", "prose two", "prose three"]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="criteria"):
            get_prose_acs(None)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            get_prose_acs([42])

    def test_none_in_list_raises_value_error(self):
        with pytest.raises(ValueError):
            get_prose_acs([None])


# ---------------------------------------------------------------------------
# ensure_boundary_and_error_coverage — core detection logic
# ---------------------------------------------------------------------------


class TestEnsureBoundaryAndErrorCoverage:
    def test_empty_list_returns_false_false(self):
        assert ensure_boundary_and_error_coverage([]) == (False, False)

    def test_prose_with_boundary_keyword(self):
        result = ensure_boundary_and_error_coverage(["handles empty input"])
        assert result == (True, False)

    def test_prose_with_error_keyword(self):
        result = ensure_boundary_and_error_coverage(["raises on invalid data"])
        assert result == (False, True)

    def test_prose_with_both_keywords(self):
        result = ensure_boundary_and_error_coverage(
            ["handles null input and raises ValueError"]
        )
        assert result == (True, True)

    def test_structural_only_returns_false_false(self):
        criteria = [
            "File exists: src/bob3/handler.py",
            "Function defined: bob3.handler.process",
            "pytest: tests/test_handler.py",
            "integration: bob3.memory",
        ]
        assert ensure_boundary_and_error_coverage(criteria) == (False, False)

    # The key regression tests: slug tokens must NOT satisfy coverage
    def test_slug_with_failing_does_not_satisfy_error_coverage(self):
        """Feature slug 'failing' must not count as 'fail' error coverage."""
        criteria = [
            "File exists: src/bob3/failing_tests_handler.py",
            "Function defined: bob3.failing_tests_handler.process",
            "pytest: tests/test_failing_tests_handler.py",
        ]
        has_boundary, has_error = ensure_boundary_and_error_coverage(criteria)
        assert not has_error, (
            "Structural AC slug 'failing' must not satisfy error coverage; "
            "word-boundary regex on prose-only ACs required"
        )

    def test_slug_with_length_capped_does_not_satisfy_boundary_coverage(self):
        """Feature slug 'length-capped' must not count as 'limit' boundary coverage."""
        criteria = [
            "File exists: src/bob3/derived_module_slug_length_capped.py",
            "Function defined: bob3.derived_module_slug_length_capped.cap",
            "pytest: tests/test_derived_module_slug_length_capped.py",
        ]
        has_boundary, has_error = ensure_boundary_and_error_coverage(criteria)
        assert not has_boundary, (
            "Structural AC slug 'length-capped' must not satisfy boundary coverage"
        )

    def test_word_boundary_required_for_boundary_keywords(self):
        """'minimum' must match as a word, not 'minimums'."""
        # 'minimums' does NOT have \b after 's', so it should NOT match 'minimum' alone
        # Actually \b(minimum)\b DOES match in 'minimums' because 'minimum' ends before 's'
        # which IS a word character, so \bminimum\b does NOT match 'minimums'
        result = ensure_boundary_and_error_coverage(["the minimums are stored"])
        # 'minimums' — 'm' at end of 'minimum' is followed by 's' which is \w,
        # so \bminimum\b does NOT match
        assert result[0] is False

    def test_word_boundary_boundary_keyword_exact_match(self):
        result = ensure_boundary_and_error_coverage(["handles boundary conditions"])
        assert result[0] is True

    def test_word_boundary_error_keyword_exact_match(self):
        result = ensure_boundary_and_error_coverage(["must raise on error"])
        assert result[1] is True

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            ensure_boundary_and_error_coverage(None)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            ensure_boundary_and_error_coverage([42])

    def test_returns_tuple_of_bools(self):
        result = ensure_boundary_and_error_coverage([])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], bool)

    def test_does_not_mutate_input(self):
        original = ["The function processes data.", "File exists: src/foo.py"]
        copy = list(original)
        ensure_boundary_and_error_coverage(original)
        assert original == copy

    def test_boundary_keywords_all_recognized(self):
        keywords = [
            "empty", "null", "none", "zero", "negative", "maximum", "minimum",
            "max", "min", "boundary", "edge case", "corner case", "overflow",
            "underflow", "limit", "threshold", "floor", "ceiling",
        ]
        for kw in keywords:
            result = ensure_boundary_and_error_coverage([f"handles {kw} input"])
            assert result[0] is True, f"keyword '{kw}' not recognized as boundary"

    def test_error_keywords_all_recognized(self):
        keywords = [
            "error", "exception", "fail", "invalid", "reject", "raise", "abort",
            "refuse", "block", "does not", "cannot", "must not", "shall not",
            "ValueError", "KeyError", "TypeError", "RuntimeError",
        ]
        for kw in keywords:
            result = ensure_boundary_and_error_coverage([f"must handle {kw} case"])
            assert result[1] is True, f"keyword '{kw}' not recognized as error"

    def test_case_insensitive_matching(self):
        assert ensure_boundary_and_error_coverage(["EMPTY input"])[0] is True
        assert ensure_boundary_and_error_coverage(["RAISE ValueError"])[1] is True

    def test_pytest_ac_with_boundary_desc_detected(self):
        """pytest: ACs with trailing description should contribute their prose."""
        # The pytest: prefix filters by the AC AC prefix detector,
        # but the description in get_prose_acs filters the whole line.
        # The key: pytest: lines ARE structural and excluded entirely.
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns well-defined result"
        ]
        # This is structural (starts with 'pytest:'), so excluded — no boundary detection
        result = ensure_boundary_and_error_coverage(criteria)
        assert result == (False, False)

    def test_prose_boundary_ac_injected_format_detected(self):
        """When a non-structural AC contains boundary keywords, it's detected."""
        criteria = [
            "empty, zero, or minimum input returns a well-defined result rather than raising"
        ]
        result = ensure_boundary_and_error_coverage(criteria)
        assert result[0] is True

    def test_prose_error_ac_injected_format_detected(self):
        """When a non-structural AC contains error keywords, it's detected."""
        criteria = [
            "invalid input raises ValueError and the function does not silently succeed"
        ]
        result = ensure_boundary_and_error_coverage(criteria)
        assert result[1] is True

    def test_idempotent_on_repeated_calls(self):
        criteria = ["handles zero input gracefully"]
        r1 = ensure_boundary_and_error_coverage(criteria)
        r2 = ensure_boundary_and_error_coverage(criteria)
        assert r1 == r2

    def test_large_ac_list_does_not_raise(self):
        criteria = [f"Criterion number {i}" for i in range(1000)]
        result = ensure_boundary_and_error_coverage(criteria)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Integration: dark_factory.boundary_error_coverage ↔ bob3.reward_hacking_detector
# ---------------------------------------------------------------------------


class TestIntegrationWithRewardHackingDetector:
    """Verify dark_factory.boundary_error_coverage is importable and usable
    from the same Python environment as bob3.reward_hacking_detector."""

    def test_reward_hacking_detector_importable(self):
        import bob3.reward_hacking_detector  # noqa: F401

    def test_dark_factory_importable_alongside_bob3(self):
        import dark_factory.boundary_error_coverage  # noqa: F401
        import bob3.reward_hacking_detector  # noqa: F401

    def test_ensure_and_get_prose_importable_together(self):
        from dark_factory.boundary_error_coverage import (
            ensure_boundary_and_error_coverage,
            get_prose_acs,
        )
        assert callable(ensure_boundary_and_error_coverage)
        assert callable(get_prose_acs)

    def test_combined_detection_on_real_feature_acs(self):
        """Simulate a real feature's AC set and verify detection is correct."""
        # This mimics the "Derived module slug MUST be length-capped" feature
        # which caused 0.0 composite due to "limit" matching in slug
        criteria = [
            "File exists: src/bob3/derived_module_slug.py",
            "Function defined: bob3.derived_module_slug.cap_slug",
            "pytest: tests/test_derived_module_slug_length_capped.py",
            "integration: bob3.spec_synthesizer",
        ]
        has_boundary, has_error = ensure_boundary_and_error_coverage(criteria)
        # All structural — no prose ACs — so both False
        assert not has_boundary
        assert not has_error
