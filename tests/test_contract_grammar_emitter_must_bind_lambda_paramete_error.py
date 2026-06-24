"""Error path tests for contract_grammar emitter lambda binding.

Tests that invalid input raises ValueError (or ContractGrammarBindingError,
a subclass of ValueError) and the function does not silently succeed.

Feature: 1efb826d-04fc-4b5b-82ed-3ba6cfcb6738
AC: pytest: tests/test_contract_grammar_emitter_must_bind_lambda_paramete_error.py
"""

import pytest

from bob.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
    validate_lambda_binding,
)
from bob.spec_quality.contract_grammar import validate_lambda_bindings


def test_validate_lambda_binding_raises_on_zero_arg_lambda():
    """Zero-arg lambda with free variable raises ContractGrammarBindingError."""
    broken = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(broken)


def test_validate_lambda_binding_raises_on_partially_unbound():
    """Partially-bound lambda raises ContractGrammarBindingError."""
    partially_broken = "@icontract.require(lambda x: (x > 0 and y < 10))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(partially_broken)


def test_validate_lambda_binding_raises_is_value_error_subclass():
    """ContractGrammarBindingError is a subclass of ValueError."""
    broken = "@icontract.require(lambda: (z > 0))"
    with pytest.raises(ValueError):
        validate_lambda_binding(broken)


def test_validate_lambda_bindings_plural_raises_on_unbound():
    """The plural alias validate_lambda_bindings also raises on unbound vars."""
    broken = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_bindings(broken)


def test_validate_lambda_binding_does_not_silently_succeed_on_unbound():
    """Validate function must not return True for a broken zero-arg lambda."""
    broken = "@icontract.require(lambda: (x > 0))"
    raised = False
    try:
        result = validate_lambda_binding(broken)
        # If no exception raised, result must not be True
        assert result is not True, "validate_lambda_binding returned True for unbound lambda"
    except ContractGrammarBindingError:
        raised = True
    assert raised, "Expected ContractGrammarBindingError to be raised"
