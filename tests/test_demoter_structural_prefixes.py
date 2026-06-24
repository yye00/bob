"""Tests for bob.demoter.is_structural_prefix_match (F-f192b763).

Verifies that the structural prefix matcher:
  - Matches ONLY at START-OF-STRING (not mid-sentence substrings)
  - Correctly classifies real structural ACs as structural
  - Does NOT classify prose ACs that quote prefix tokens mid-sentence
  - Handles non-string input gracefully (returns False)
  - Positive test: a real "pytest: tests/foo.py" criterion routes to pytest
  - Regression: a prose AC containing "pytest:" mid-sentence DEMOTES (not structural)
"""
import pytest

from bob.demoter import is_structural_prefix_match


class TestStartOfStringPrefixRequired:
    """is_structural_prefix_match MUST use start-of-string position, not substring."""

    def test_pytest_colon_at_start_is_structural(self):
        """Real pytest criterion starting with 'pytest:' is structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_colon_mid_sentence_is_not_structural(self):
        """Prose quoting 'pytest:' mid-sentence must NOT be classified structural.

        This is the 15d1ac4f regression: AC text containing "entries with prefix
        'pytest:'" was falsely classified as structural because the old code used
        substring matching.
        """
        prose = (
            "behavior: collect_feature_test_paths returns the set of test paths "
            "declared in the feature's AC list (entries with prefix 'pytest:') "
            "plus tests/<feature_id>/ if it exists; returns empty set when "
            "feature has no pytest ACs"
        )
        assert is_structural_prefix_match(prose) is False

    def test_file_exists_at_start_is_structural(self):
        """'file exists: src/foo.py' starting with 'file exists:' is structural."""
        assert is_structural_prefix_match("file exists: src/foo.py") is True

    def test_file_exists_mid_sentence_is_not_structural(self):
        """Prose mentioning 'file exists:' mid-sentence must NOT be structural."""
        prose = "behavior: verify that file exists: src/foo.py is present"
        assert is_structural_prefix_match(prose) is False

    def test_function_defined_at_start_is_structural(self):
        """'function defined: bob.module.func' is structural."""
        assert is_structural_prefix_match("function defined: bob.module.func") is True

    def test_function_defined_mid_sentence_is_not_structural(self):
        """Prose quoting 'function defined:' mid-sentence is prose, not structural."""
        prose = "ensure that function defined: my_func meets the spec"
        assert is_structural_prefix_match(prose) is False

    def test_integration_at_start_is_structural(self):
        """'integration: bob.run_loop' at start is structural."""
        assert is_structural_prefix_match("integration: bob.run_loop") is True

    def test_class_defined_at_start_is_structural(self):
        """'class defined: MyClass' is structural."""
        assert is_structural_prefix_match("class defined: MyClass") is True


class TestWhitespaceHandling:
    """Leading whitespace must be stripped before checking the prefix."""

    def test_leading_spaces_stripped(self):
        """Leading spaces should not prevent a match."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_leading_tab_stripped(self):
        """Leading tab should not prevent a match."""
        assert is_structural_prefix_match("\tfile exists: src/bar.py") is True


class TestNonStringInput:
    """Non-string inputs must return False without raising."""

    def test_none_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_int_returns_false(self):
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]

    def test_bytes_returns_false(self):
        assert is_structural_prefix_match(b"pytest: tests/foo.py") is False  # type: ignore[arg-type]

    def test_list_returns_false(self):
        assert is_structural_prefix_match(["pytest: tests/foo.py"]) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False


class TestRealPytestRoutingRegression:
    """Positive test: a real pytest: criterion must be correctly identified as structural.

    This ensures that fixing the mid-sentence false-positive does not break
    the real structural detection.
    """

    def test_real_pytest_criterion_is_structural(self):
        """pytest: tests/foo.py must be classified structural (routes to pytest)."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_real_pytest_with_flags_is_structural(self):
        """pytest: tests/foo.py -v must be classified structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py -v") is True

    def test_real_pytest_with_path_is_structural(self):
        """pytest: tests/test_bar.py::TestClass must be classified structural."""
        assert is_structural_prefix_match("pytest: tests/test_bar.py::TestClass") is True


class TestAllKnownPrefixes:
    """Every registered structural prefix must match at start-of-string."""

    @pytest.mark.parametrize("prefix", [
        "pytest:",
        "python:",
        "ci tests:",
        "file exists:",
        "function defined:",
        "class defined:",
        "integration:",
        "forbidden_imports:",
        "behavioral_signature:",
        "deterministic_output:",
        "resource_limit:",
        "mms:",
    ])
    def test_known_prefix_at_start_is_structural(self, prefix: str):
        """Each known prefix followed by a space and content must be structural."""
        criterion = f"{prefix} some content"
        assert is_structural_prefix_match(criterion) is True, (
            f"Expected {criterion!r} to be classified as structural"
        )
