"""Boundary cases for backend_required_check (feature c28dbe93).

Empty / whitespace / minimum input returns a well-defined result rather than
raising.
"""

from hippy.backend_required_check import (
    is_harness_feature,
    backend_required_check,
)


def test_empty_title_is_not_harness():
    assert is_harness_feature("") is False


def test_whitespace_title_is_not_harness():
    assert is_harness_feature("   \n  ") is False


def test_empty_title_backend_not_required():
    result = backend_required_check("")
    assert result["is_harness"] is False
    assert result["backend_required"] is False


def test_whitespace_backend_check_well_defined():
    result = backend_required_check("   ")
    assert set(result) >= {"is_harness", "backend_required", "reason"}
    assert result["backend_required"] is False


def test_single_harness_word_minimum_input():
    assert is_harness_feature("xfail") is True


def test_none_description_defaults_gracefully():
    # description=None is a valid absence, not an error.
    result = backend_required_check("xfail taxonomy", description=None)
    assert result["is_harness"] is True
    assert result["backend_required"] is False
