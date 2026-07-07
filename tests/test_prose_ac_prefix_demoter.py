"""Regression tests for the prose-AC / integration-AC prefix demoter (F-R7-578).

These tests encode the defect from bob v.16 round 13 feature 15d1ac4f, which
was NH'd thrice because:

  (a) prose AC text quoting "entries with prefix 'pytest:'" mid-sentence falsely
      satisfied the substring marker `"pytest:"` and was classified structural,
  (b) integration body "regression-sweep ... continues to run whole-suite pytest
      separately" did not match the limited connector list and fell through to
      a hard-fail.

The fix: structural prefixes must match at START-of-string (not substring), and
the prose connector registry must cover the policy phrases.
"""
import pytest

from bob.prose_ac_demoter import (
    is_structural_prefix_match,
    is_executable_or_structural_criterion,
    is_prose_ac,
    demote_if_prose,
    get_prose_connectors,
)


# The exact 15d1ac4f prose AC that quotes 'pytest:' mid-sentence.
PROSE_QUOTING_PYTEST = (
    "behavior: collect_feature_test_paths returns the set of test paths "
    "declared in the feature's AC list (entries with prefix 'pytest:') plus "
    "tests/<feature_id>/ if it exists; returns empty set when feature has no "
    "pytest ACs"
)

# The exact 15d1ac4f integration body.
INTEGRATION_PROSE = (
    "integration: regression-sweep / F-R7-532 invariant pass continues to run "
    "whole-suite pytest separately (no behavior regression for the cross-feature "
    "regression detection path)"
)


class TestStructuralPrefixIsStartOfString:
    def test_mid_sentence_pytest_quote_is_not_structural(self):
        """Prose AC quoting 'pytest:' mid-sentence must NOT match structurally."""
        assert is_structural_prefix_match(PROSE_QUOTING_PYTEST) is False

    def test_real_pytest_criterion_matches(self):
        """A real 'pytest: tests/foo.py' criterion must match structurally."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_leading_whitespace_still_matches(self):
        """Leading whitespace is stripped before the prefix check."""
        assert is_structural_prefix_match("   pytest: tests/foo.py") is True

    def test_file_exists_prefix_matches(self):
        assert is_structural_prefix_match("File exists: src/bob/x.py") is True

    def test_function_defined_prefix_matches(self):
        assert is_structural_prefix_match("Function defined: bob.x.y") is True


class TestIsExecutableOrStructuralCriterion:
    def test_prose_quoting_pytest_is_not_executable(self):
        """A2/A1 regression: prose quoting 'pytest:' must NOT be executable."""
        assert is_executable_or_structural_criterion(PROSE_QUOTING_PYTEST) is False

    def test_integration_prose_is_not_executable(self):
        """The 15d1ac4f integration prose body must demote (not executable)."""
        assert is_executable_or_structural_criterion(INTEGRATION_PROSE) is False

    def test_real_pytest_criterion_is_executable(self):
        """A3: a real pytest criterion must route to executable verification."""
        assert is_executable_or_structural_criterion("pytest: tests/foo.py") is True

    def test_file_exists_is_executable(self):
        """A4: 'File exists:' is structural/executable."""
        assert is_executable_or_structural_criterion("File exists: tests/foo.py") is True

    def test_substring_marker_still_executable(self):
        """Keyword markers ('function implemented') remain executable mid-sentence."""
        assert is_executable_or_structural_criterion(
            "the parser function implemented correctly"
        ) is True

    def test_non_string_is_not_executable(self):
        assert is_executable_or_structural_criterion(None) is False


class TestProseDemotion:
    def test_prose_quoting_pytest_demotes(self):
        """The AC quoting 'pytest:' mid-sentence must demote (not hard-fail)."""
        assert is_prose_ac(PROSE_QUOTING_PYTEST) is True
        result = demote_if_prose(PROSE_QUOTING_PYTEST)
        assert result is not None
        assert result[0] is True

    def test_integration_prose_demotes(self):
        assert is_prose_ac(INTEGRATION_PROSE) is True
        assert demote_if_prose(INTEGRATION_PROSE) is not None

    def test_real_pytest_criterion_does_not_demote(self):
        """A real pytest criterion must NOT demote — it routes to real verification."""
        assert is_prose_ac("pytest: tests/foo.py") is False
        assert demote_if_prose("pytest: tests/foo.py") is None


class TestProseConnectorRegistry:
    def test_covers_15d1ac4f_regression_tokens(self):
        registry = get_prose_connectors()
        for token in ("continues to", "separately", "invariant",
                      "whole-suite", "no behavior", "unaffected"):
            assert token in registry, f"missing connector token: {token!r}"

    def test_is_frozenset(self):
        assert isinstance(get_prose_connectors(), frozenset)
