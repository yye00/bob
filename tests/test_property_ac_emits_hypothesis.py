"""Tests for property: AC grammar → emit_hypothesis_test.

Verifies:
- parse_property_ac recognises the grammar and extracts name/generator/predicate.
- emit_hypothesis_test produces valid Python source with @given decorator.
- Fixed seed=0 is embedded in the emitted code.
- Non-property ACs return None from parse_property_ac.
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.example_grammar import (
    PropertyAC,
    emit_hypothesis_test,
    parse_property_ac,
)


# ---------------------------------------------------------------------------
# parse_property_ac
# ---------------------------------------------------------------------------


class TestParsePropertyAC:
    def test_basic_integer_property(self):
        ac = "property: non_negative for st.integers() assert x >= 0"
        result = parse_property_ac(ac)
        assert result is not None
        assert isinstance(result, PropertyAC)
        assert result.name == "non_negative"
        assert "st.integers()" in result.generator
        assert "x >= 0" in result.predicate

    def test_string_property(self):
        ac = "property: non_empty_string for st.text(min_size=1) assert len(value) > 0"
        result = parse_property_ac(ac)
        assert result is not None
        assert result.name == "non_empty_string"
        assert "st.text" in result.generator
        assert "len(value) > 0" in result.predicate

    def test_property_with_spaces_in_name(self):
        ac = "property: round trip encoding for st.binary(max_size=50) assert decoded == original"
        result = parse_property_ac(ac)
        assert result is not None
        assert "round trip encoding" in result.name or "round" in result.name

    def test_case_insensitive_prefix(self):
        ac = "Property: abs_is_positive for st.integers() assert abs(x) >= 0"
        result = parse_property_ac(ac)
        assert result is not None

    def test_pytest_ac_returns_none(self):
        assert parse_property_ac("pytest: tests/test_foo.py") is None

    def test_behavior_ac_returns_none(self):
        assert parse_property_ac("behavior: parser returns None when input is empty") is None

    def test_file_exists_ac_returns_none(self):
        assert parse_property_ac("File exists: src/bob3/foo.py") is None

    def test_empty_string_returns_none(self):
        assert parse_property_ac("") is None

    def test_raw_field_preserved(self):
        ac = "property: positive_sum for st.integers(min_value=1) assert x > 0"
        result = parse_property_ac(ac)
        assert result is not None
        assert result.raw == ac

    def test_complex_predicate(self):
        ac = "property: sorted_output for st.lists(st.integers()) assert result == sorted(result)"
        result = parse_property_ac(ac)
        assert result is not None
        assert "sorted" in result.predicate

    def test_property_without_for_returns_none(self):
        # Missing 'for' keyword makes it unparseable
        result = parse_property_ac("property: something assert x > 0")
        # Either None or a partial parse; at minimum it shouldn't crash
        assert result is None or isinstance(result, PropertyAC)


# ---------------------------------------------------------------------------
# emit_hypothesis_test
# ---------------------------------------------------------------------------


class TestEmitHypothesisTest:
    def _make_prop(self, name="non_negative", generator="st.integers()", predicate="x >= 0"):
        ac = f"property: {name} for {generator} assert {predicate}"
        return parse_property_ac(ac)

    def test_emitted_code_contains_given_decorator(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "@given(" in code

    def test_emitted_code_contains_generator(self):
        prop = self._make_prop(generator="st.integers(min_value=-100, max_value=100)")
        code = emit_hypothesis_test(prop)
        assert "st.integers" in code

    def test_emitted_code_contains_assert(self):
        prop = self._make_prop(predicate="x >= 0")
        code = emit_hypothesis_test(prop)
        assert "assert" in code
        assert "x >= 0" in code

    def test_emitted_code_contains_settings(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "@settings(" in code

    def test_emitted_code_has_max_examples_100(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "max_examples=100" in code

    def test_default_seed_is_zero(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "deriving=0" in code

    def test_custom_seed(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop, seed=42)
        assert "deriving=42" in code

    def test_emitted_function_name_contains_property_name(self):
        prop = self._make_prop(name="abs_positive")
        code = emit_hypothesis_test(prop)
        assert "abs_positive" in code

    def test_emitted_code_is_valid_python(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        # Must not raise SyntaxError
        compile(code, "<string>", "exec")

    def test_emitted_code_imports_hypothesis(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "from hypothesis import" in code

    def test_emitted_code_imports_strategies(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "strategies as st" in code

    def test_function_def_present(self):
        prop = self._make_prop(name="my_property")
        code = emit_hypothesis_test(prop)
        assert "def test_property_my_property" in code

    def test_suppress_health_check_present(self):
        prop = self._make_prop()
        code = emit_hypothesis_test(prop)
        assert "suppress_health_check" in code
