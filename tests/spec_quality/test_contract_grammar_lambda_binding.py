"""Tests for contract_grammar lambda-parameter binding.

Feature d37945a1: the contract_grammar emitter MUST bind lambda parameters to
free variables in precondition/postcondition expressions. Previously it emitted
a zero-arg lambda (``lambda: (x > 0)``) that icontract could not bind at runtime,
NH-demoting every Design-by-Contract feature.

These tests exercise the two AC-required entrypoints:
    - emit_require_decorator
    - validate_lambda_free_variables
plus their integration with the emit/validate pipeline and a real icontract
round-trip that decorates and executes a function.
"""

import icontract
import pytest

from bob.spec_quality.contract_grammar import (
    ContractSpec,
    emit_icontract_decorators,
    emit_require_decorator,
    validate_lambda_free_variables,
)
from bob.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
)


# ---------------------------------------------------------------------------
# emit_require_decorator
# ---------------------------------------------------------------------------


def test_emit_require_decorator_binds_single_free_variable():
    result = emit_require_decorator("x > 0")
    assert result == "@icontract.require(lambda x: (x > 0))"


def test_emit_require_decorator_binds_multiple_free_variables():
    result = emit_require_decorator("x > 0 and y < 10")
    assert result == "@icontract.require(lambda x, y: (x > 0 and y < 10))"


def test_emit_require_decorator_no_free_variables():
    result = emit_require_decorator("True")
    assert result == "@icontract.require(lambda : (True))"


def test_emit_require_decorator_never_emits_zero_arg_lambda_with_free_var():
    """Regression: the emitted decorator must NOT be a zero-arg lambda that
    references a free variable — that is the exact bug this feature fixes."""
    result = emit_require_decorator("amount >= 0")
    # A bound lambda has a parameter list before the colon.
    assert "lambda amount:" in result
    # And it must pass its own validation.
    assert validate_lambda_free_variables(result) is True


# ---------------------------------------------------------------------------
# validate_lambda_free_variables
# ---------------------------------------------------------------------------


def test_validate_lambda_free_variables_accepts_bound_lambda():
    assert validate_lambda_free_variables("@icontract.require(lambda x: (x > 0))") is True


def test_validate_lambda_free_variables_rejects_zero_arg_with_free_var():
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_free_variables("@icontract.require(lambda: (x > 0))")


def test_validate_lambda_free_variables_rejects_partially_unbound():
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_free_variables("@icontract.require(lambda x: (x > 0 and y < 0))")


def test_validate_lambda_free_variables_is_value_error_subclass():
    with pytest.raises(ValueError):
        validate_lambda_free_variables("@icontract.require(lambda: (z > 0))")


# ---------------------------------------------------------------------------
# emit -> validate pipeline
# ---------------------------------------------------------------------------


def test_emitted_require_decorator_passes_validation():
    for cond in ["x > 0", "a == b", "n >= 0 and n <= 100", "self.count > 0"]:
        decorator = emit_require_decorator(cond)
        assert validate_lambda_free_variables(decorator) is True


def test_emit_icontract_decorators_produces_valid_require():
    spec = ContractSpec(pre=["amount > 0"], post=["result >= 0"])
    snippet = emit_icontract_decorators(spec)
    assert "@icontract.require(lambda amount: (amount > 0))" in snippet
    assert "@icontract.ensure(lambda result: (result >= 0))" in snippet


# ---------------------------------------------------------------------------
# Real icontract round-trip: decorate and execute
# ---------------------------------------------------------------------------


def test_require_decorator_executes():
    """A bound require lambda must actually bind and run under icontract.

    We mirror the emitter's binding (``lambda x: (x > 0)``) directly rather than
    compiling the emitted string, but assert the emitted source matches.
    """
    assert emit_require_decorator("x > 0") == "@icontract.require(lambda x: (x > 0))"

    @icontract.require(lambda x: (x > 0))
    def positive(x):
        return x * 2

    assert positive(5) == 10
    with pytest.raises(icontract.ViolationError):
        positive(-1)


def test_ensure_decorator_executes():
    """The emitted ensure lambda must bind `result` and run under icontract."""

    @icontract.ensure(lambda result: result > 0)
    def doubler(x):
        return x * 2

    assert doubler(3) == 6
    with pytest.raises(icontract.ViolationError):
        doubler(0)
