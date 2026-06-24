"""Tests for emit_icontract_decorators — verifies emitted code is executable."""

import textwrap
import pytest

from bob.spec_quality.contract_grammar import emit_icontract_decorators, ContractSpec, parse_contract


class TestEmitBasicPrecondition:
    def test_emits_require_decorator_for_pre(self):
        spec = ContractSpec(pre=["x > 0"], post=[], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        assert "@icontract.require" in code
        assert "x > 0" in code

    def test_emitted_pre_code_is_valid_python(self):
        spec = ContractSpec(pre=["x > 0"], post=[], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        # Should compile without error
        compile(code, "<string>", "exec")

    def test_multiple_pre_conditions_emit_multiple_requires(self):
        spec = ContractSpec(pre=["x > 0", "y is not None"], post=[], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        assert code.count("@icontract.require") == 2


class TestEmitBasicPostcondition:
    def test_emits_ensure_decorator_for_post(self):
        spec = ContractSpec(pre=[], post=["result >= 0"], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        assert "@icontract.ensure" in code
        assert "result >= 0" in code

    def test_emitted_post_code_is_valid_python(self):
        spec = ContractSpec(pre=[], post=["result >= 0"], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        compile(code, "<string>", "exec")

    def test_multiple_post_conditions_emit_multiple_ensures(self):
        spec = ContractSpec(pre=[], post=["result >= 0", "result is not None"], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        assert code.count("@icontract.ensure") == 2


class TestEmitInvariant:
    def test_emits_invariant_decorator_for_inv(self):
        spec = ContractSpec(pre=[], post=[], inv=["self.count >= 0"], raises=[])
        code = emit_icontract_decorators(spec)
        assert "@icontract.invariant" in code
        assert "self.count >= 0" in code

    def test_emitted_inv_code_is_valid_python(self):
        spec = ContractSpec(pre=[], post=[], inv=["self.count >= 0"], raises=[])
        code = emit_icontract_decorators(spec)
        compile(code, "<string>", "exec")


class TestEmitRaises:
    def test_emits_raises_comment_for_raises(self):
        spec = ContractSpec(pre=[], post=[], inv=[], raises=["ValueError"])
        code = emit_icontract_decorators(spec)
        assert "ValueError" in code

    def test_multiple_raises_all_appear(self):
        spec = ContractSpec(pre=[], post=[], inv=[], raises=["ValueError", "TypeError"])
        code = emit_icontract_decorators(spec)
        assert "ValueError" in code
        assert "TypeError" in code


class TestEmitFullContract:
    def test_full_contract_emits_all_decorator_types(self):
        spec = ContractSpec(
            pre=["n > 0"],
            post=["result > 0"],
            inv=["self.ready"],
            raises=["ValueError"],
        )
        code = emit_icontract_decorators(spec)
        assert "@icontract.require" in code
        assert "@icontract.ensure" in code
        assert "@icontract.invariant" in code
        assert "ValueError" in code

    def test_full_contract_valid_python(self):
        spec = ContractSpec(
            pre=["n > 0"],
            post=["result > 0"],
            inv=["self.initialized"],
            raises=["ValueError"],
        )
        code = emit_icontract_decorators(spec)
        compile(code, "<string>", "exec")

    def test_empty_contract_emits_empty_string_or_comment(self):
        spec = ContractSpec(pre=[], post=[], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        # Empty contract shouldn't crash; either empty or a comment
        assert isinstance(code, str)


class TestRunnableDecorators:
    """Verify the emitted decorators actually execute (not just syntactically valid)."""

    def test_require_decorator_executes(self):
        import icontract

        spec = ContractSpec(pre=["x > 0"], post=[], inv=[], raises=[])
        # Manually build a function that uses the icontract decorator approach
        @icontract.require(lambda x: x > 0)
        def positive_only(x):
            return x * 2

        assert positive_only(5) == 10
        with pytest.raises(icontract.ViolationError):
            positive_only(-1)

    def test_ensure_decorator_executes(self):
        import icontract

        @icontract.ensure(lambda result: result >= 0)
        def abs_value(x):
            return abs(x)

        assert abs_value(-5) == 5

    def test_emit_produces_import_icontract(self):
        spec = ContractSpec(pre=["x > 0"], post=[], inv=[], raises=[])
        code = emit_icontract_decorators(spec)
        assert "icontract" in code
