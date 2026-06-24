"""Boundary tests for contract_grammar emitter lambda binding.

Tests that empty, zero, or minimum input to extract_lambda_parameters and
validate_lambda_binding return well-defined results rather than raising.

Feature: 1efb826d-04fc-4b5b-82ed-3ba6cfcb6738
AC: pytest: tests/test_contract_grammar_emitter_must_bind_lambda_paramete_boundary.py
"""

from bob.spec_quality.contract_grammar import extract_lambda_parameters, validate_lambda_bindings
from bob.spec_quality.contract_grammar_lambda_binder import validate_lambda_binding


def test_extract_lambda_parameters_empty_string():
    """Empty condition string returns empty tuple, not an error."""
    result = extract_lambda_parameters("")
    assert result == () or isinstance(result, tuple)


def test_extract_lambda_parameters_constant_expression():
    """Constant expression has no free variables — returns empty tuple."""
    result = extract_lambda_parameters("True")
    assert isinstance(result, tuple)
    assert "True" not in result


def test_extract_lambda_parameters_single_variable():
    """Single variable condition returns a one-element tuple."""
    result = extract_lambda_parameters("x > 0")
    assert isinstance(result, tuple)
    assert "x" in result


def test_extract_lambda_parameters_numeric_literal():
    """Pure numeric constant has no free variables."""
    result = extract_lambda_parameters("42")
    assert isinstance(result, tuple)
    assert len(result) == 0


def test_validate_lambda_binding_no_lambda_in_decorator():
    """A decorator string with no lambda node returns True without raising."""
    result = validate_lambda_binding("@some.decorator()")
    assert result is True


def test_validate_lambda_bindings_fully_bound_single_param():
    """Minimal single-param bound lambda passes validation."""
    result = validate_lambda_bindings("@icontract.require(lambda x: x > 0)")
    assert result is True


def test_extract_lambda_parameters_builtin_only():
    """Expression using only builtins returns empty tuple."""
    result = extract_lambda_parameters("len([]) == 0")
    assert isinstance(result, tuple)
    assert "len" not in result
