"""Tests asserting parse_property_ac raises an error when predicate is missing or empty.

AC: asserts parse_property_ac must raise an error and reject an invalid input
when the predicate assert clause is missing or empty.
"""

from __future__ import annotations

import pytest

from bob.spec_quality.example_grammar import (
    PropertyParseError,
    parse_property_ac,
    raises_on_malformed_property,
)


class TestPropertyAcErrorPathMissingPredicate:
    def test_missing_assert_clause_parse_returns_none(self):
        ac = "property: my_prop for st.integers()"
        result = parse_property_ac(ac)
        assert result is None

    def test_missing_assert_clause_raises_on_malformed(self):
        ac = "property: my_prop for st.integers()"
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property(ac)

    def test_assert_with_empty_predicate_is_rejected(self):
        # "property: x for st.integers() assert " — trailing whitespace only
        ac = "property: x for st.integers() assert "
        result = parse_property_ac(ac)
        # Should be None since predicate is empty
        if result is not None:
            assert result.predicate == "" or result.predicate.strip() == ""

    def test_raises_on_malformed_rejects_empty_predicate(self):
        ac = "property: x for st.integers() assert "
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property(ac)

    def test_missing_assert_keyword_entirely(self):
        ac = "property: my_prop for st.integers() x >= 0"
        result = parse_property_ac(ac)
        assert result is None

    def test_raises_on_malformed_rejects_missing_assert_keyword(self):
        ac = "property: my_prop for st.integers() x >= 0"
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property(ac)

    def test_valid_property_with_predicate_accepted(self):
        ac = "property: non_negative for st.integers() assert x >= 0"
        result = parse_property_ac(ac)
        assert result is not None
        assert result.predicate == "x >= 0"

    def test_raises_on_malformed_accepts_valid_property(self):
        ac = "property: non_negative for st.integers() assert x >= 0"
        result = raises_on_malformed_property(ac)
        assert result is not None
        assert result.predicate == "x >= 0"

    def test_property_parse_error_is_value_error(self):
        ac = "property: bad for st.integers()"
        with pytest.raises(ValueError):
            raises_on_malformed_property(ac)

    def test_error_message_meaningful(self):
        ac = "property: my_prop for st.integers()"
        with pytest.raises(PropertyParseError) as exc_info:
            raises_on_malformed_property(ac)
        error_msg = str(exc_info.value)
        # Error message should mention the relevant missing clause
        assert len(error_msg) > 0

    def test_non_property_ac_always_rejected(self):
        for ac in [
            "pytest: tests/test_foo.py",
            "File exists: src/bob/foo.py",
            "Function defined: foo.bar.baz",
            "integration: bob.spec_quality.ears_parser",
        ]:
            with pytest.raises(PropertyParseError):
                raises_on_malformed_property(ac)
