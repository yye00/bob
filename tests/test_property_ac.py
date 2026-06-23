"""Tests for bob3.property_ac: register_property_assertion and generate_hypothesis_tests."""

from __future__ import annotations

import pytest

from bob3.property_ac import generate_hypothesis_tests, register_property_assertion
from bob3.spec_quality.example_grammar import PropertyAC


class TestRegisterPropertyAssertion:
    def test_valid_property_ac_registered(self):
        registry: dict[str, PropertyAC] = {}
        prop = register_property_assertion(registry, "property: non_negative for st.integers() assert x >= 0")
        assert prop.name == "non_negative"
        assert "non_negative" in registry
        assert registry["non_negative"] is prop

    def test_returns_property_ac_dataclass(self):
        registry: dict[str, PropertyAC] = {}
        prop = register_property_assertion(registry, "property: p for st.integers() assert True")
        assert isinstance(prop, PropertyAC)

    def test_stores_generator_and_predicate(self):
        registry: dict[str, PropertyAC] = {}
        prop = register_property_assertion(
            registry, "property: bounded for st.integers(min_value=0) assert x >= 0"
        )
        assert "integers" in prop.generator
        assert "x >= 0" in prop.predicate

    def test_multiple_properties_all_registered(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: a for st.integers() assert True")
        register_property_assertion(registry, "property: b for st.text() assert len(x) >= 0")
        assert "a" in registry
        assert "b" in registry
        assert len(registry) == 2

    def test_duplicate_name_overwrites(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: p for st.integers() assert True")
        prop2 = register_property_assertion(registry, "property: p for st.text() assert len(x) >= 0")
        assert registry["p"] is prop2

    def test_missing_for_clause_raises_value_error(self):
        registry: dict[str, PropertyAC] = {}
        with pytest.raises(ValueError, match="for"):
            register_property_assertion(registry, "property: p assert x > 0")

    def test_missing_assert_clause_raises_value_error(self):
        registry: dict[str, PropertyAC] = {}
        with pytest.raises(ValueError, match="assert"):
            register_property_assertion(registry, "property: p for st.integers()")

    def test_empty_string_raises_value_error(self):
        registry: dict[str, PropertyAC] = {}
        with pytest.raises(ValueError):
            register_property_assertion(registry, "")

    def test_non_property_ac_raises_value_error(self):
        registry: dict[str, PropertyAC] = {}
        with pytest.raises(ValueError):
            register_property_assertion(registry, "pytest: tests/test_foo.py")

    def test_registry_unchanged_on_error(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: valid for st.integers() assert True")
        with pytest.raises(ValueError):
            register_property_assertion(registry, "property: bad assert x > 0")
        assert "valid" in registry
        assert "bad" not in registry


class TestGenerateHypothesisTests:
    def test_empty_registry_returns_empty_dict(self):
        result = generate_hypothesis_tests({})
        assert result == {}

    def test_single_property_generates_test(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: non_negative for st.integers() assert x >= 0 or x < 0")
        tests = generate_hypothesis_tests(registry)
        assert "non_negative" in tests
        assert "@given" in tests["non_negative"]

    def test_generated_test_is_valid_python(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: t for st.integers() assert True")
        tests = generate_hypothesis_tests(registry)
        compile(tests["t"], "<string>", "exec")

    def test_generated_test_contains_seed(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: t for st.integers() assert True")
        tests = generate_hypothesis_tests(registry, seed=0)
        assert "0" in tests["t"]

    def test_multiple_properties_all_emitted(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: a for st.integers() assert True")
        register_property_assertion(registry, "property: b for st.text() assert len(x) >= 0")
        tests = generate_hypothesis_tests(registry)
        assert "a" in tests
        assert "b" in tests
        assert len(tests) == 2

    def test_generated_test_contains_generator(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: t for st.integers() assert True")
        tests = generate_hypothesis_tests(registry)
        assert "st.integers()" in tests["t"]

    def test_result_keys_match_property_names(self):
        registry: dict[str, PropertyAC] = {}
        register_property_assertion(registry, "property: alpha for st.integers() assert True")
        tests = generate_hypothesis_tests(registry)
        assert set(tests.keys()) == {"alpha"}
