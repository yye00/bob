"""Boundary tests: empty / zero / minimum input returns a well-defined
result rather than raising (feature 5420e867)."""

from hippy.checks.backend_required_call_site import (
    has_real_call_site,
    has_simulation_marker,
)


def test_empty_string_has_no_call_site():
    assert has_real_call_site("") is False


def test_empty_string_has_no_simulation_marker():
    assert has_simulation_marker("") is False


def test_whitespace_only_has_no_call_site():
    assert has_real_call_site("   \n\t  \n") is False


def test_whitespace_only_has_no_simulation_marker():
    assert has_simulation_marker("   \n\t  \n") is False


def test_single_char_returns_bool():
    assert has_real_call_site("x") is False
    assert has_simulation_marker("x") is False


def test_import_only_minimum_returns_false():
    assert has_real_call_site("import hipblas") is False
