"""Tests for bob.demoter.is_structural_prefix_match (F-0234e7b3).

Verifies the public API exposed via bob.demoter wraps the correct
prefix-position matching logic from bob.verification.structural_prefix_match.
"""
import pytest

from bob.demoter import is_structural_prefix_match


class TestIsStructuralPrefixMatch:
    def test_pytest_at_start_returns_true(self):
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_mid_sentence_returns_false(self):
        """Prose AC quoting 'pytest:' mid-sentence must NOT be structural."""
        criterion = (
            "behavior: foo returns entries with prefix 'pytest:' "
            "plus tests/<feature_id>/ if it exists"
        )
        assert is_structural_prefix_match(criterion) is False

    def test_file_exists_at_start_returns_true(self):
        assert is_structural_prefix_match("file exists: src/foo.py") is True

    def test_function_defined_at_start_returns_true(self):
        assert is_structural_prefix_match("function defined: bob.demoter.is_structural_prefix_match") is True

    def test_class_defined_at_start_returns_true(self):
        assert is_structural_prefix_match("class defined: bob.SomeClass") is True

    def test_integration_at_start_returns_true(self):
        assert is_structural_prefix_match("integration: bob.x.y routes through z") is True

    def test_python_at_start_returns_true(self):
        assert is_structural_prefix_match("python: import sys; sys.version") is True

    def test_integration_mid_sentence_returns_false(self):
        """'integration:' appearing after other text is not a leading prefix match."""
        criterion = "behavior: foo triggers integration: bar baz"
        assert is_structural_prefix_match(criterion) is False

    def test_leading_whitespace_stripped(self):
        """Leading whitespace should be stripped before prefix check."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_behavior_prefix_returns_false(self):
        """'behavior:' is NOT a structural prefix — it signals prose description."""
        assert is_structural_prefix_match("behavior: some description") is False

    def test_non_string_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]
        assert is_structural_prefix_match(123) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_exact_15d1ac4f_prose_criterion_returns_false(self):
        """The 15d1ac4f regression: prose AC quoting 'pytest:' mid-sentence demotes."""
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(criterion) is False

    def test_real_pytest_routes_to_structural(self):
        """A criterion starting with 'pytest:' should be classified structural."""
        assert is_structural_prefix_match("pytest: tests/test_foo.py") is True

    def test_case_insensitive_prefix_match(self):
        """Prefix matching should be case-insensitive."""
        assert is_structural_prefix_match("Pytest: tests/foo.py") is True
        assert is_structural_prefix_match("FILE EXISTS: src/x.py") is True
