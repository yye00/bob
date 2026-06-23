"""Tests for bob3.acceptance_criteria.property_based.PropertyBasedAC."""

from __future__ import annotations

import pytest

from bob3.acceptance_criteria.property_based import PropertyBasedAC, PropertyParseError


class TestPropertyBasedACFromString:
    def test_valid_property_ac_parsed(self):
        pb = PropertyBasedAC.from_string(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert pb.name == "non_negative"
        assert pb.generator == "st.integers()"
        assert pb.predicate == "x >= 0"

    def test_from_string_missing_for_raises(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property: p assert x > 0")

    def test_from_string_missing_assert_raises(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property: p for st.integers()")

    def test_property_parse_error_is_value_error(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property: p for st.integers()")

    def test_raw_preserved(self):
        raw = "property: non_negative for st.integers() assert x >= 0"
        pb = PropertyBasedAC.from_string(raw)
        assert pb.raw == raw


class TestPropertyBasedACTryParse:
    def test_valid_property_ac_returns_instance(self):
        pb = PropertyBasedAC.try_parse(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert pb is not None
        assert pb.name == "non_negative"

    def test_none_returns_none(self):
        assert PropertyBasedAC.try_parse(None) is None

    def test_empty_string_returns_none(self):
        assert PropertyBasedAC.try_parse("") is None

    def test_non_property_ac_returns_none(self):
        assert PropertyBasedAC.try_parse("pytest: tests/test_foo.py") is None

    def test_malformed_property_ac_raises(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.try_parse("property: p assert x > 0")


class TestPropertyBasedACHypothesisTest:
    def test_hypothesis_test_contains_given(self):
        pb = PropertyBasedAC.from_string(
            "property: non_negative for st.integers() assert x >= 0"
        )
        code = pb.hypothesis_test()
        assert "@given" in code

    def test_hypothesis_test_compiles(self):
        pb = PropertyBasedAC.from_string(
            "property: non_negative for st.integers() assert x >= 0"
        )
        code = pb.hypothesis_test(seed=0)
        compile(code, "<string>", "exec")

    def test_hypothesis_test_seed_in_code(self):
        pb = PropertyBasedAC.from_string(
            "property: p for st.integers() assert True"
        )
        code = pb.hypothesis_test(seed=42)
        assert "42" in code


class TestPropertyBasedACProperties:
    def test_few_shot_snippet_format(self):
        pb = PropertyBasedAC.from_string(
            "property: non_negative for st.integers() assert x >= 0"
        )
        snippet = pb.few_shot_snippet
        assert "property: non_negative" in snippet
        assert "st.integers()" in snippet
        assert "x >= 0" in snippet

    def test_name_property(self):
        pb = PropertyBasedAC.from_string(
            "property: my_prop for st.text() assert len(x) >= 0"
        )
        assert pb.name == "my_prop"

    def test_generator_property(self):
        pb = PropertyBasedAC.from_string(
            "property: p for st.text() assert len(x) >= 0"
        )
        assert pb.generator == "st.text()"

    def test_predicate_property(self):
        pb = PropertyBasedAC.from_string(
            "property: p for st.text() assert len(x) >= 0"
        )
        assert pb.predicate == "len(x) >= 0"
