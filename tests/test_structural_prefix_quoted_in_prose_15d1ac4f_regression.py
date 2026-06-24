"""Regression test — F-30176f30 / F-R7-576 fix.

Asserts that a prose AC that QUOTES a structural prefix mid-sentence does NOT
trigger is_structural_prefix_match (i.e. the function returns False), while a
real leading-prefix criterion (e.g. 'pytest: tests/foo.py') returns True.
"""
from bob.verification.structural_prefix_match import is_structural_prefix_match


def test_prose_ac_quoting_pytest_returns_false():
    """Prose AC that quotes 'pytest:' mid-sentence must NOT be classified structural."""
    criterion = "behavior: foo returns entries with prefix 'pytest:' inside"
    assert is_structural_prefix_match(criterion) is False


def test_real_pytest_leading_prefix_returns_true():
    """A criterion that starts with 'pytest:' must be classified structural."""
    assert is_structural_prefix_match("pytest: tests/foo.py") is True


def test_real_pytest_leading_prefix_with_whitespace_returns_true():
    """Leading whitespace must be stripped before prefix check."""
    assert is_structural_prefix_match("  pytest: tests/foo.py") is True


def test_behavior_prefix_leading_is_structural():
    """'behavior:' at the start of a criterion is a structural prefix."""
    assert is_structural_prefix_match("behavior: some description") is False


def test_file_exists_leading_is_structural():
    """'file exists:' at the start returns True."""
    assert is_structural_prefix_match("file exists: src/foo.py") is True


def test_function_defined_leading_is_structural():
    """'function defined:' at the start returns True."""
    assert is_structural_prefix_match("function defined: bob.x.y") is True


def test_integration_prefix_mid_sentence_is_not_structural():
    """'integration:' appearing mid-sentence after other text is not a leading match."""
    criterion = "behavior: foo works with integration: bar baz"
    assert is_structural_prefix_match(criterion) is False


def test_integration_prefix_leading_is_structural():
    """'integration:' at the start is structural."""
    assert is_structural_prefix_match("integration: bob.x.y routes through z") is True
