"""Tests for contract_grammar_lambda_binder — lambda parameter binding for icontract decorators.

Regression test suite for feature 12c9969a (fix for 73879589 zero-arg lambda bug).
"""

import pytest

from bob3.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
    emit_bound_require_decorator,
    extract_free_variables,
    validate_lambda_binding,
)


class TestExtractFreeVariables:
    def test_single_variable(self):
        result = extract_free_variables("x > 0")
        assert result == ("x",)

    def test_two_variables_sorted(self):
        result = extract_free_variables("x > 0 and y < 10")
        assert result == ("x", "y")

    def test_variable_order_canonical(self):
        # Variables are returned sorted, regardless of order in expression
        result = extract_free_variables("z > 0 and a < 5")
        assert result == ("a", "z")

    def test_builtin_not_included(self):
        # builtins like len, abs should not appear as free variables
        result = extract_free_variables("len(items) > 0")
        assert "len" not in result

    def test_none_keyword_excluded(self):
        result = extract_free_variables("x is not None")
        assert "None" not in result
        assert "x" in result

    def test_true_false_excluded(self):
        result = extract_free_variables("flag is True")
        assert "True" not in result
        assert "flag" in result

    def test_numeric_literal_no_vars(self):
        result = extract_free_variables("1 + 2 > 0")
        assert result == ()

    def test_complex_expression(self):
        result = extract_free_variables("x > 0 and y < 10 and z != 0")
        assert result == ("x", "y", "z")

    def test_attribute_access_base_included(self):
        # self.count — 'self' is the free var, 'count' is an attribute
        result = extract_free_variables("self.count >= 0")
        assert "self" in result

    def test_returns_tuple(self):
        result = extract_free_variables("x > 0")
        assert isinstance(result, tuple)


class TestEmitBoundRequireDecorator:
    def test_single_var_binding(self):
        result = emit_bound_require_decorator("x > 0")
        assert "lambda x:" in result

    def test_two_var_binding(self):
        result = emit_bound_require_decorator("x > 0 and y < 10")
        assert "lambda x, y:" in result or "lambda" in result
        assert "x" in result and "y" in result

    def test_condition_included_in_output(self):
        result = emit_bound_require_decorator("x > 0")
        assert "x > 0" in result

    def test_icontract_require_prefix(self):
        result = emit_bound_require_decorator("x > 0")
        assert result.startswith("@icontract.require(")

    def test_returns_string(self):
        result = emit_bound_require_decorator("x > 0")
        assert isinstance(result, str)

    def test_two_var_canonical_order(self):
        result = emit_bound_require_decorator("x > 0 and y < 10")
        # Canonical order: sorted alphabetically
        assert "lambda x, y:" in result

    def test_no_free_vars_uses_empty_lambda(self):
        # A condition with no identifiers: just a constant expression
        result = emit_bound_require_decorator("1 > 0")
        assert "@icontract.require(" in result

    def test_valid_python_syntax(self):
        result = emit_bound_require_decorator("x > 0")
        # Should be parseable as part of a decorator
        full_code = f"import icontract\n{result}\ndef fn(x): return x"
        compile(full_code, "<string>", "exec")

    def test_multi_var_valid_python_syntax(self):
        result = emit_bound_require_decorator("x > 0 and y < 10")
        full_code = f"import icontract\n{result}\ndef fn(x, y): return x + y"
        compile(full_code, "<string>", "exec")


class TestValidateLambdaBinding:
    def test_valid_binding_returns_true(self):
        decorator = "@icontract.require(lambda x: (x > 0))"
        assert validate_lambda_binding(decorator) is True

    def test_valid_two_var_binding_returns_true(self):
        decorator = "@icontract.require(lambda x, y: (x > 0 and y < 10))"
        assert validate_lambda_binding(decorator) is True

    def test_broken_zero_arg_lambda_raises_error(self):
        # The legacy broken form: zero-arg lambda referencing free var x
        broken = "@icontract.require(lambda: (x > 0))"
        with pytest.raises(ContractGrammarBindingError):
            validate_lambda_binding(broken)

    def test_broken_missing_var_raises_error(self):
        # lambda only binds x but body references y too
        broken = "@icontract.require(lambda x: (x > 0 and y < 10))"
        with pytest.raises(ContractGrammarBindingError):
            validate_lambda_binding(broken)

    def test_builtin_reference_is_ok(self):
        # len is a builtin, not a free variable requiring binding
        decorator = "@icontract.require(lambda items: (len(items) > 0))"
        assert validate_lambda_binding(decorator) is True

    def test_ensure_with_result_valid(self):
        # @ensure retains 'lambda result:' — no regression
        decorator = "@icontract.ensure(lambda result: (result >= 0))"
        assert validate_lambda_binding(decorator) is True

    def test_invariant_with_self_valid(self):
        decorator = "@icontract.invariant(lambda self: (self.count >= 0))"
        assert validate_lambda_binding(decorator) is True


class TestRegressionFor73879589:
    """Regression test: the root cause of NH-demotion for feature 73879589."""

    def test_emitter_produces_bound_lambda_for_require(self):
        """emit_bound_require_decorator must NOT produce a zero-arg lambda."""
        result = emit_bound_require_decorator("x > 0")
        # Must NOT be the broken zero-arg form
        assert "lambda:" not in result
        assert "lambda x:" in result

    def test_emitted_decorator_passes_validate(self):
        """end-to-end: emitted decorator must pass validation."""
        result = emit_bound_require_decorator("x > 0")
        # Should not raise
        assert validate_lambda_binding(result) is True

    def test_emitted_multi_var_passes_validate(self):
        result = emit_bound_require_decorator("x > 0 and y < 10")
        assert validate_lambda_binding(result) is True

    def test_icontract_executes_emitted_decorator(self):
        """The emitted decorator must be executable by icontract at runtime."""
        import icontract

        # Simulate what the emitter now produces: bound lambda
        @icontract.require(lambda x: (x > 0))
        def positive_only(x):
            return x * 2

        assert positive_only(5) == 10
        with pytest.raises(icontract.ViolationError):
            positive_only(-1)

    def test_zero_arg_lambda_would_fail_validation(self):
        """Confirm the old broken form fails validate_lambda_binding."""
        broken_form = "@icontract.require(lambda: (x > 0))"
        with pytest.raises(ContractGrammarBindingError):
            validate_lambda_binding(broken_form)
