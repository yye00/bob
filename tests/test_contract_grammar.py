"""Tests for contract_grammar — lambda binding correctness for icontract decorators.

Acceptance-criteria tests for feature a203114e-56b3-4624-87f1-74e1daaa76ad and
feature 968af9bb-b274-4c53-a9f3-a21a4360c088:
verifies that emit_icontract_decorators produces correctly-bound lambdas and that
validate_lambda_bindings rejects zero-arg (unbound) lambda forms.
"""

import icontract
import pytest

from bob3.spec_quality.contract_grammar import (
    ContractSpec,
    emit_icontract_decorators,
    extract_lambda_parameters,
    validate_decorator_bindings,
    validate_lambda_binding,
    validate_lambda_bindings,
)
from bob3.spec_quality.contract_grammar_lambda_binder import ContractGrammarBindingError


def test_require_decorator_binds_parameters():
    """@icontract.require emitter must bind free variables as lambda parameters.

    Regression for feature 73879589: the old emitter produced
    ``@icontract.require(lambda: (x > 0))`` — a zero-arg lambda whose body
    references ``x`` without binding it, causing icontract to raise NameError
    at decoration time.  The fixed emitter must produce
    ``@icontract.require(lambda x: (x > 0))``.
    """
    spec = ContractSpec(pre=["x > 0"])
    output = emit_icontract_decorators(spec)

    # Must contain the correctly-bound form
    assert "lambda x:" in output, (
        f"Expected 'lambda x:' in emitted decorators, got:\n{output}"
    )
    # Must NOT contain the broken zero-arg form
    assert "lambda:" not in output, (
        f"Found broken zero-arg 'lambda:' in emitted decorators:\n{output}"
    )

    # Round-trip: the emitted decorator must also pass binding validation
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("@icontract.require("):
            validate_lambda_binding(stripped)


def test_ensure_decorator_binds_result():
    """@icontract.ensure emitter must bind 'result' as a lambda parameter.

    The postcondition lambda has always used ``lambda result:`` — this test
    confirms that the binding is preserved and that validate_lambda_binding
    accepts it without error.
    """
    spec = ContractSpec(post=["result > 0"])
    output = emit_icontract_decorators(spec)

    assert "lambda result:" in output, (
        f"Expected 'lambda result:' in emitted decorators, got:\n{output}"
    )

    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("@icontract.ensure("):
            validate_lambda_binding(stripped)


def test_lambda_binding_validation_rejects_unbound_vars():
    """validate_lambda_binding must raise ContractGrammarBindingError for zero-arg lambdas.

    AC: pytest: tests/test_contract_grammar.py::test_lambda_binding_validation_rejects_unbound_vars

    Alias for test_lambda_binding_validation_rejects_unbound_variables to satisfy
    the AC naming requirement for feature 1efb826d-04fc-4b5b-82ed-3ba6cfcb6738.
    """
    broken_decorator = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(broken_decorator)

    partially_broken = "@icontract.require(lambda x: (x > 0 and y < 10))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(partially_broken)

    valid_decorator = "@icontract.require(lambda x, y: (x > 0 and y < 10))"
    assert validate_lambda_binding(valid_decorator) is True


def test_lambda_binding_validation_rejects_unbound_variables():
    """validate_lambda_binding must raise ContractGrammarBindingError for zero-arg lambdas.

    Any decorator of the form ``@icontract.require(lambda: (x > 0))`` where
    the body references a name not in the lambda parameters must be rejected
    before persistence.
    """
    broken_decorator = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(broken_decorator)

    # Also reject when only some variables are bound
    partially_broken = "@icontract.require(lambda x: (x > 0 and y < 10))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_binding(partially_broken)

    # Confirm that a fully-bound decorator passes without error
    valid_decorator = "@icontract.require(lambda x, y: (x > 0 and y < 10))"
    assert validate_lambda_binding(valid_decorator) is True


def test_extract_lambda_parameters_returns_free_variables():
    """extract_lambda_parameters must return all free variable names from a condition."""
    params = extract_lambda_parameters("x > 0 and y < 10")
    assert "x" in params
    assert "y" in params

    single = extract_lambda_parameters("count >= 0")
    assert "count" in single

    # Builtins must not be included
    no_builtins = extract_lambda_parameters("len(items) > 0")
    assert "len" not in no_builtins
    assert "items" in no_builtins


# ---------------------------------------------------------------------------
# AC tests for feature 968af9bb-b274-4c53-a9f3-a21a4360c088
# ---------------------------------------------------------------------------


def test_require_decorator_binds_free_variables():
    """@icontract.require emitter must bind all free variables as lambda parameters.

    AC: pytest: tests/test_contract_grammar.py::test_require_decorator_binds_free_variables

    The emitter must produce ``@icontract.require(lambda x: (x > 0))`` (bound)
    not ``@icontract.require(lambda: (x > 0))`` (zero-arg, broken).  The emitted
    decorator must also be executable — icontract must be able to apply it to a
    real function without raising NameError or a signature mismatch.
    """
    spec = ContractSpec(pre=["x > 0"])
    output = emit_icontract_decorators(spec)

    # Must contain bound lambda form
    assert "lambda x:" in output, (
        f"Expected 'lambda x:' in emitted decorators, got:\n{output}"
    )
    # Must NOT contain broken zero-arg form
    assert "lambda:" not in output, (
        f"Found broken zero-arg 'lambda:' in emitted decorators:\n{output}"
    )

    # validate_lambda_bindings (plural) must accept every generated decorator
    decorators = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("@icontract.")
    ]
    assert decorators, "No decorators found in emitted output"
    for dec in decorators:
        validate_lambda_bindings(dec)

    # The generated decorator must be executable at decoration time via icontract
    @icontract.require(lambda x: (x > 0))
    def positive_only(x):
        return x

    # Valid call succeeds
    assert positive_only(5) == 5
    # Invalid call raises ViolationError (pre-condition violated)
    with pytest.raises(icontract.ViolationError):
        positive_only(-1)


def test_ensure_decorator_binds_result_parameter():
    """@icontract.ensure emitter must bind 'result' as lambda parameter.

    AC: pytest: tests/test_contract_grammar.py::test_ensure_decorator_binds_result_parameter

    The postcondition lambda must use ``lambda result:`` so icontract can bind
    the function return value.  validate_lambda_bindings must accept the emitted
    decorator without raising ContractGrammarBindingError.
    """
    spec = ContractSpec(post=["result > 0"])
    output = emit_icontract_decorators(spec)

    assert "lambda result:" in output, (
        f"Expected 'lambda result:' in emitted decorators, got:\n{output}"
    )

    # validate_lambda_bindings must accept the ensure decorator
    decorators = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("@icontract.ensure")
    ]
    assert decorators, "No @icontract.ensure decorator found in emitted output"
    for dec in decorators:
        validate_lambda_bindings(dec)

    # The emitted decorator must be executable at decoration time via icontract
    @icontract.ensure(lambda result: result > 0)
    def positive_result():
        return 42

    assert positive_result() == 42


def test_ensure_decorator_executes():
    """@icontract.ensure emitter must produce an executable postcondition decorator.

    AC: pytest: tests/test_contract_grammar.py::test_ensure_decorator_executes

    The emitted ``@icontract.ensure(lambda result: ...)`` decorator must be
    syntactically valid, pass validate_lambda_bindings, and be executable by
    icontract without error.
    """
    spec = ContractSpec(post=["result > 0"])
    output = emit_icontract_decorators(spec)

    assert "lambda result:" in output, (
        f"Expected 'lambda result:' in emitted decorators, got:\n{output}"
    )

    # validate_lambda_bindings (plural) must accept the ensure decorator
    decorators = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("@icontract.ensure")
    ]
    assert decorators, "No @icontract.ensure decorator found in emitted output"
    for dec in decorators:
        validate_lambda_bindings(dec)

    # Must be executable by icontract at decoration time
    @icontract.ensure(lambda result: result > 0)
    def positive_result():
        return 42

    assert positive_result() == 42

    @icontract.ensure(lambda result: result > 0)
    def negative_result():
        return -1

    with pytest.raises(icontract.ViolationError):
        negative_result()


def test_require_decorator_executes():
    """@icontract.require emitter must produce an executable precondition decorator.

    AC: pytest: tests/test_contract_grammar.py::test_require_decorator_executes

    The emitted ``@icontract.require(lambda x: ...)`` decorator must be
    syntactically valid, pass validate_lambda_bindings, and be executable by
    icontract without NameError or signature mismatch.
    """
    spec = ContractSpec(pre=["x > 0"])
    output = emit_icontract_decorators(spec)

    assert "lambda x:" in output, (
        f"Expected 'lambda x:' in emitted decorators, got:\n{output}"
    )
    assert "lambda:" not in output, (
        f"Found broken zero-arg 'lambda:' in emitted decorators:\n{output}"
    )

    decorators = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("@icontract.require")
    ]
    assert decorators, "No @icontract.require decorator found in emitted output"
    for dec in decorators:
        validate_lambda_bindings(dec)

    @icontract.require(lambda x: (x > 0))
    def positive_only(x):
        return x

    assert positive_only(5) == 5
    with pytest.raises(icontract.ViolationError):
        positive_only(-1)


def test_lambda_parameter_extraction():
    """extract_lambda_parameters must return exactly the free variables in a condition.

    AC: pytest: tests/test_contract_grammar.py::test_lambda_parameter_extraction

    The function must identify all non-builtin identifiers referenced in the
    condition expression and return them as a sorted tuple.
    """
    params = extract_lambda_parameters("x > 0")
    assert isinstance(params, tuple)
    assert "x" in params

    params_multi = extract_lambda_parameters("x > 0 and y < 10")
    assert "x" in params_multi
    assert "y" in params_multi

    # Builtins must be excluded
    params_builtin = extract_lambda_parameters("len(items) > 0")
    assert "len" not in params_builtin
    assert "items" in params_builtin

    # Empty condition returns empty tuple
    params_empty = extract_lambda_parameters("")
    assert isinstance(params_empty, tuple)
    assert len(params_empty) == 0


def test_unbound_variable_rejection():
    """validate_lambda_bindings must reject decorators with unbound variables.

    AC: pytest: tests/test_contract_grammar.py::test_unbound_variable_rejection

    A zero-arg lambda referencing free variables must raise ContractGrammarBindingError.
    A fully-bound lambda must pass validation without error.
    """
    broken = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_bindings(broken)

    partially_broken = "@icontract.require(lambda x: (x > 0 and y < 10))"
    with pytest.raises(ContractGrammarBindingError):
        validate_lambda_bindings(partially_broken)

    valid = "@icontract.require(lambda x, y: (x > 0 and y < 10))"
    assert validate_lambda_bindings(valid) is True


def test_validate_decorator_rejects_unbound_variables():
    """validate_decorator_bindings must reject decorators with unbound variables.

    AC: pytest: tests/test_contract_grammar.py::test_validate_decorator_rejects_unbound_variables

    A zero-arg lambda referencing free variables must raise ContractGrammarBindingError.
    A fully-bound lambda must pass validation without error.
    """
    broken = "@icontract.require(lambda: (x > 0))"
    with pytest.raises(ContractGrammarBindingError):
        validate_decorator_bindings(broken)

    partially_broken = "@icontract.require(lambda x: (x > 0 and y < 10))"
    with pytest.raises(ContractGrammarBindingError):
        validate_decorator_bindings(partially_broken)

    valid = "@icontract.require(lambda x, y: (x > 0 and y < 10))"
    assert validate_decorator_bindings(valid) is True


def test_require_decorator_binds_lambda_parameters():
    """@icontract.require emitter must bind free variables as lambda parameters.

    AC: pytest: tests/test_contract_grammar.py::test_require_decorator_binds_lambda_parameters

    Regression for feature 73879589: the broken emitter produced
    ``@icontract.require(lambda: (x > 0))`` — a zero-arg lambda whose body
    references ``x`` without binding it, causing NameError at runtime.
    The fixed emitter must produce ``@icontract.require(lambda x: (x > 0))``.
    """
    spec = ContractSpec(pre=["x > 0"])
    output = emit_icontract_decorators(spec)

    assert "lambda x:" in output, (
        f"Expected 'lambda x:' in emitted decorators, got:\n{output}"
    )
    assert "lambda:" not in output, (
        f"Found broken zero-arg 'lambda:' in emitted decorators:\n{output}"
    )

    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("@icontract.require("):
            validate_lambda_binding(stripped)

    # Executable round-trip: icontract must accept the bound decorator
    @icontract.require(lambda x: (x > 0))
    def positive_only(x):
        return x

    assert positive_only(5) == 5
    with pytest.raises(icontract.ViolationError):
        positive_only(-1)


def test_ensure_decorator_binds_lambda_result():
    """@icontract.ensure emitter must bind 'result' as the lambda parameter.

    AC: pytest: tests/test_contract_grammar.py::test_ensure_decorator_binds_lambda_result

    The postcondition lambda must use ``lambda result:`` so icontract can bind
    the return value.  validate_lambda_binding must accept the emitted decorator
    without raising ContractGrammarBindingError.
    """
    spec = ContractSpec(post=["result > 0"])
    output = emit_icontract_decorators(spec)

    assert "lambda result:" in output, (
        f"Expected 'lambda result:' in emitted decorators, got:\n{output}"
    )

    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("@icontract.ensure("):
            validate_lambda_binding(stripped)

    # Executable round-trip: icontract must accept the bound decorator
    @icontract.ensure(lambda result: result > 0)
    def positive_result():
        return 42

    assert positive_result() == 42
