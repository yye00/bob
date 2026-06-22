"""Test that real 'pytest:' criteria still route to _run_pytest_criterion.

The demoter MUST NOT shadow executable pytest forms. A criterion starting with
'pytest:' at the leading position must be detected as structural (not prose)
and therefore must NOT be demoted.
"""
from bob3.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
)


def test_real_pytest_criterion_is_structural():
    """'pytest: tests/test_existing.py' must be identified as structural (not prose)."""
    criterion = "pytest: tests/test_existing.py"
    assert is_structural_prefix_match(criterion) is True


def test_real_pytest_criterion_not_substring_marker():
    """A real pytest criterion does not rely on substring marker matching."""
    criterion = "pytest: tests/test_existing.py"
    # It's structural by prefix — is_substring_marker_match covers other keywords
    assert is_substring_marker_match(criterion) is False


def test_is_executable_integration_criterion_not_demoted():
    """'integration:' leading the criterion is structural — must not be prose-demoted."""
    criterion = "integration: bob3.foo.bar"
    assert is_structural_prefix_match(criterion) is True


def test_function_implemented_is_substring_marker():
    """'function implemented' must match as a substring marker."""
    assert is_substring_marker_match("function implemented in module foo") is True


def test_method_implemented_is_substring_marker():
    """'method implemented' must match as a substring marker."""
    assert is_substring_marker_match("new method implemented correctly") is True


def test_no_compilation_errors_is_substring_marker():
    """'no compilation errors' matches as a substring marker."""
    assert is_substring_marker_match("check that there are no compilation errors") is True


def test_cmake_is_substring_marker():
    """'cmake' matches as a substring marker."""
    assert is_substring_marker_match("cmake build system is wired") is True


def test_prose_phrase_is_not_substring_marker():
    """Pure policy prose does not match as a substring marker."""
    assert is_substring_marker_match("the feature should behave correctly") is False


def test_prose_phrase_quoting_pytest_is_not_structural():
    """Mid-sentence 'pytest:' quote does not make a criterion structural."""
    criterion = "behavior: collect returns entries with prefix 'pytest:' only"
    assert is_structural_prefix_match(criterion) is False
    assert is_substring_marker_match(criterion) is False
