"""Tests for bob3.demoters.is_structural_prefix_match (F-b3790872).

Verifies that:
- Prefix matching is START-OF-STRING only (not substring)
- A prose AC quoting "pytest:" mid-sentence DEMOTES (returns False)
- A real "pytest: tests/foo.py" criterion returns True (routes to pytest)
- Non-string inputs return False gracefully
"""
import pytest

from bob3.demoters import is_structural_prefix_match


class TestIsStructuralPrefixMatchStartOfString:
    """Prefix must be at START-OF-STRING — mid-sentence quotes must not match."""

    def test_real_pytest_criterion_returns_true(self):
        """A real 'pytest: tests/foo.py' criterion must route as structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_with_leading_whitespace_returns_true(self):
        """Leading whitespace is stripped before checking."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_prose_quoting_pytest_mid_sentence_returns_false(self):
        """A prose AC that mentions 'pytest:' mid-sentence must NOT match.

        This is the A1 regression case from F-b3790872: the AC text
        "entries with prefix 'pytest:'" contains the literal substring
        'pytest:' but it is NOT at start-of-string — so it must demote.
        """
        prose = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(prose) is False

    def test_file_exists_prefix_returns_true(self):
        assert is_structural_prefix_match("file exists: src/bob3/demoters.py") is True

    def test_function_defined_prefix_returns_true(self):
        assert is_structural_prefix_match("function defined: bob3.demoters.is_structural_prefix_match") is True

    def test_integration_prefix_returns_true(self):
        assert is_structural_prefix_match("integration: bob3.spec_extractor") is True

    def test_plain_prose_returns_false(self):
        assert is_structural_prefix_match("this feature does not break anything") is False

    def test_integration_prose_regression_case_returns_false(self):
        """The 15d1ac4f integration-prose regression body must NOT match as structural.

        The body starts with 'regression-sweep', not a structural prefix.
        """
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        assert is_structural_prefix_match(body) is False

    def test_case_insensitive_matching(self):
        """Prefix matching must be case-insensitive."""
        assert is_structural_prefix_match("PYTEST: tests/foo.py") is True
        assert is_structural_prefix_match("File Exists: src/foo.py") is True

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_none_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_integer_returns_false(self):
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]

    def test_list_does_not_return_true(self):
        result = is_structural_prefix_match(["pytest: foo"])  # type: ignore[arg-type]
        assert result is not True

    def test_python_prefix_returns_true(self):
        assert is_structural_prefix_match("python: src/bob3/demoters.py") is True

    def test_class_defined_prefix_returns_true(self):
        assert is_structural_prefix_match("class defined: bob3.demoters.Demoter") is True
