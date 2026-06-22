"""Tests for emit_parametrize_block — verifies seed=0 reproducibility.

ACs require emit_parametrize_block (alias for emit_parametrize_test) with seed=0
by default, ensuring generated parametrized tests are reproducible.
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.example_grammar import (
    KeyExample,
    emit_parametrize_block,
)


def _ex(given: str, then: str) -> KeyExample:
    return KeyExample(given=given, then=then, raw=f"given: {given}, then: {then}")


class TestEmitParametrizeBlockSeedZero:
    def test_default_seed_is_zero(self):
        examples = [_ex("x=5", "25")]
        code = emit_parametrize_block(examples)
        assert "seed=0" in code

    def test_seed_zero_comment_present(self):
        examples = [_ex("x=1", "1")]
        code = emit_parametrize_block(examples)
        assert "# seed=0" in code

    def test_calling_twice_same_output(self):
        examples = [_ex("x=5", "25"), _ex("x=0", "0")]
        code1 = emit_parametrize_block(examples)
        code2 = emit_parametrize_block(examples)
        assert code1 == code2

    def test_same_examples_same_seed_reproducible(self):
        examples = [_ex("x=3", "9"), _ex("x=-1", "error")]
        result_a = emit_parametrize_block(examples, seed=0)
        result_b = emit_parametrize_block(examples, seed=0)
        assert result_a == result_b

    def test_different_seed_different_comment(self):
        examples = [_ex("x=5", "25")]
        code0 = emit_parametrize_block(examples, seed=0)
        code42 = emit_parametrize_block(examples, seed=42)
        assert "seed=0" in code0
        assert "seed=42" in code42
        assert code0 != code42

    def test_emitted_code_is_valid_python(self):
        examples = [_ex("x=5", "25"), _ex("x=0", "0")]
        code = emit_parametrize_block(examples)
        compile(code, "<string>", "exec")

    def test_emitted_code_contains_parametrize(self):
        examples = [_ex("x=5", "25")]
        code = emit_parametrize_block(examples)
        assert "@pytest.mark.parametrize" in code

    def test_emitted_code_imports_pytest(self):
        examples = [_ex("x=1", "1")]
        code = emit_parametrize_block(examples)
        assert "import pytest" in code

    def test_all_examples_appear_in_output(self):
        examples = [_ex("x=0", "0"), _ex("x=100", "100"), _ex("x=-1", "error")]
        code = emit_parametrize_block(examples)
        assert "x=0" in code
        assert "x=100" in code
        assert "x=-1" in code

    def test_empty_list_returns_empty_string(self):
        assert emit_parametrize_block([]) == ""

    def test_custom_test_name_used(self):
        examples = [_ex("x=1", "1")]
        code = emit_parametrize_block(examples, test_name="test_my_feature")
        assert "test_my_feature" in code

    def test_assert_present_in_emitted_code(self):
        examples = [_ex("x=5", "25")]
        code = emit_parametrize_block(examples)
        assert "assert" in code
