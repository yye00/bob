"""Tests for bob3.criterion_demoter.is_structural_prefix_match (F-0234e7b3).

Key regression tests:
- A prose AC containing "pytest:" mid-sentence DEMOTES (not hard-fails).
- A real "pytest: tests/foo.py" criterion still routes to pytest dispatch.
"""
import pytest

from bob3.demoter import is_structural_prefix_match


class TestIsStructuralPrefixMatchBasics:
    """Core prefix-position contract."""

    def test_pytest_at_start_is_structural(self):
        """'pytest: tests/foo.py' starts with 'pytest:' — structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_with_leading_whitespace_is_structural(self):
        """Leading whitespace before 'pytest:' should be stripped — still structural."""
        assert is_structural_prefix_match("  pytest: tests/bar.py") is True

    def test_file_exists_at_start_is_structural(self):
        assert is_structural_prefix_match("file exists: tests/foo.py") is True

    def test_function_defined_at_start_is_structural(self):
        assert is_structural_prefix_match("function defined: bob3.demoter.is_structural_prefix_match") is True

    def test_class_defined_at_start_is_structural(self):
        assert is_structural_prefix_match("class defined: bob3.SomeClass") is True

    def test_integration_at_start_is_structural(self):
        assert is_structural_prefix_match("integration: bob3.regression_detector") is True

    def test_none_input_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_whitespace_only_returns_false(self):
        assert is_structural_prefix_match("   ") is False


class TestProseQuotingPytestMidSentence:
    """The core regression: prose mentioning 'pytest:' mid-sentence must NOT classify as structural."""

    def test_prose_quoting_pytest_mid_sentence_is_not_structural(self):
        """
        Regression A1: 15d1ac4f prose-quoting-pytest.

        The behavior AC text:
            "behavior: collect_feature_test_paths returns the set of
             test paths declared in the feature's AC list (entries with
             prefix 'pytest:') plus tests/<feature_id>/ if it exists;
             returns empty set when feature has no pytest ACs"
        must return False — 'pytest:' here is a quoted reference, not a
        prefix marker.
        """
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        result = is_structural_prefix_match(criterion)
        assert result is False, (
            "Prose AC quoting 'pytest:' mid-sentence was classified as structural. "
            "Only START-OF-STRING position counts."
        )

    def test_behavior_prefix_is_not_structural(self):
        """Criteria starting with 'behavior:' are definitionally prose — not structural."""
        assert is_structural_prefix_match("behavior: foo does X") is False

    def test_prose_mentioning_file_exists_mid_sentence(self):
        """'file exists:' mentioned in prose mid-sentence is not structural."""
        criterion = "This criterion checks that file exists: src/foo.py but this is prose."
        # The prefix appears mid-sentence (after other words), so is_structural_prefix_match
        # should return False because the start is 'This criterion...' not 'file exists:'
        result = is_structural_prefix_match(criterion)
        assert result is False

    def test_prose_with_pytest_colon_in_parenthetical(self):
        """A parenthetical '(e.g., pytest: tests/x.py)' mid-sentence must not classify as structural."""
        criterion = "behavior: the system dispatches tests (e.g., pytest: tests/x.py) correctly"
        assert is_structural_prefix_match(criterion) is False


class TestRealPytestCriterionRouting:
    """A real 'pytest: tests/foo.py' criterion must return True so it routes to pytest dispatch."""

    def test_real_pytest_criterion_returns_true(self):
        """'pytest: tests/foo.py' is structural and should route to pytest dispatch."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_with_subdir_path_returns_true(self):
        assert is_structural_prefix_match("pytest: tests/verification/test_demoter.py") is True

    def test_pytest_with_options_returns_true(self):
        assert is_structural_prefix_match("pytest: tests/test_foo.py -v") is True

    def test_pytest_lowercase_is_structural(self):
        assert is_structural_prefix_match("pytest: tests/test_something.py") is True
