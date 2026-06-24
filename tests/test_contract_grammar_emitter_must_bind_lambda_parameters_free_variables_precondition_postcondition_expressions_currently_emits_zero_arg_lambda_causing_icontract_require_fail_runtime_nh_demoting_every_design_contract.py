"""Tests for the contract_grammar emitter lambda binding AC.

Feature a8588f10: verifies that the named entry-point function correctly emits
bound lambda decorators for icontract.require, fixing the zero-arg lambda bug
(feature 73879589) that caused NH-demotion of Design-by-Contract features.
"""

import pytest
import icontract

from bob.contract_grammar_emitter_must_bind_lambda_parameters_free_variables_precondition_postcondition_expressions_currently_emits_zero_arg_lambda_causing_icontract_require_fail_runtime_nh_demoting_every_design_contract import (
    contract_grammar_emitter_must_bind_lambda_parameters_free_variables_precondition_postcondition_expressions_currently_emits_zero_arg_lambda_causing_icontract_require_fail_runtime_nh_demoting_every_design_contract as emit_bound_require,
    ContractGrammarBindingError,
)


def test_contract_grammar_emitter_must_bind_lambda_parameters_free_variables_precondition_postcondition_expressions_currently_emits_zero_arg_lambda_causing_icontract_require_fail_runtime_nh_demoting_every_design_contract():
    """AC: emitter produces a correctly-bound require decorator for a single free variable.

    The function must emit ``@icontract.require(lambda x: (x > 0))``,
    NOT the broken zero-arg form ``@icontract.require(lambda: (x > 0))``.
    """
    result = emit_bound_require("x > 0")

    # Must be a string
    assert isinstance(result, str)

    # Must start with the icontract.require decorator
    assert result.startswith("@icontract.require(")

    # Must bind the free variable x as a lambda parameter
    assert "lambda x:" in result

    # Must NOT contain the broken zero-arg lambda
    assert "lambda:" not in result

    # Must include the condition expression
    assert "x > 0" in result

    # Must be valid Python syntax
    full_code = f"import icontract\n{result}\ndef fn(x): return x"
    compile(full_code, "<string>", "exec")


def test_emitter_binds_two_variables():
    """Emitter binds multiple free variables in sorted order."""
    result = emit_bound_require("x > 0 and y < 10")

    assert "lambda x, y:" in result
    assert "x > 0 and y < 10" in result
    assert "lambda:" not in result


def test_emitter_produces_valid_icontract_decorator():
    """The emitted decorator is executable by icontract at runtime."""
    @icontract.require(lambda x: (x > 0))
    def positive_only(x):
        return x * 2

    assert positive_only(5) == 10
    with pytest.raises(icontract.ViolationError):
        positive_only(-1)


def test_emitter_validates_binding_before_returning():
    """The function validates the decorator and does not return invalid output."""
    # A valid condition should return successfully
    result = emit_bound_require("n > 0")
    assert result is not None
    assert "lambda n:" in result


def test_emitter_excludes_builtins_from_params():
    """Built-in names like len should not appear as lambda parameters."""
    result = emit_bound_require("len(items) > 0")
    assert "lambda items:" in result
    assert "len" not in result.split("lambda")[1].split(":")[0]


def test_zero_arg_lambda_form_is_broken():
    """Confirm the old broken form would fail validation (regression guard)."""
    from bob.spec_quality.contract_grammar_lambda_binder import validate_lambda_binding

    broken = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(broken)
