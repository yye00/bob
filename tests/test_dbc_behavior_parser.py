"""Tests for bob.dbc_behavior_parser — Design-by-Contract sub-grammar parser.

Covers parse_dbc_behavior and DBCBehavior for the four optional sub-keys:
pre, post, inv, raises.
"""

from __future__ import annotations

import pytest

from bob.dbc_behavior_parser import DBCBehavior, parse_dbc_behavior


class TestDBCBehaviorDataclass:
    """DBCBehavior is a dataclass with spec, decorators, and blame fields."""

    def test_dbc_behavior_has_spec(self):
        result = parse_dbc_behavior({})
        assert hasattr(result, "spec")

    def test_dbc_behavior_has_decorators(self):
        result = parse_dbc_behavior({})
        assert hasattr(result, "decorators")

    def test_dbc_behavior_has_blame(self):
        result = parse_dbc_behavior({})
        assert hasattr(result, "blame")

    def test_dbc_behavior_is_dbc_behavior_instance(self):
        result = parse_dbc_behavior({})
        assert isinstance(result, DBCBehavior)


class TestParseDBC_EmptyInput:
    """Empty dict returns well-defined zero-state result."""

    def test_empty_dict_spec_pre_empty(self):
        result = parse_dbc_behavior({})
        assert result.spec["pre"] == []

    def test_empty_dict_spec_post_empty(self):
        result = parse_dbc_behavior({})
        assert result.spec["post"] == []

    def test_empty_dict_spec_inv_empty(self):
        result = parse_dbc_behavior({})
        assert result.spec["inv"] == []

    def test_empty_dict_spec_raises_empty(self):
        result = parse_dbc_behavior({})
        assert result.spec["raises"] == []

    def test_empty_dict_decorators_empty_string(self):
        result = parse_dbc_behavior({})
        assert result.decorators == ""

    def test_empty_dict_blame_empty_dict(self):
        result = parse_dbc_behavior({})
        assert result.blame == {}


class TestParseDBC_PreCondition:
    """pre sub-key maps to icontract.require decorator, blame=caller."""

    def test_pre_parsed_into_spec(self):
        result = parse_dbc_behavior({"pre": "x > 0"})
        assert result.spec["pre"] == ["x > 0"]

    def test_pre_blame_is_caller(self):
        result = parse_dbc_behavior({"pre": "x > 0"})
        assert result.blame["pre"] == "caller"

    def test_pre_decorator_contains_require(self):
        result = parse_dbc_behavior({"pre": "x > 0"})
        assert "icontract" in result.decorators or "require" in result.decorators

    def test_pre_list_of_clauses(self):
        result = parse_dbc_behavior({"pre": ["x > 0", "y >= 0"]})
        assert result.spec["pre"] == ["x > 0", "y >= 0"]

    def test_pre_blame_not_implementer(self):
        result = parse_dbc_behavior({"pre": "x > 0"})
        assert result.blame.get("pre") != "implementer"


class TestParseDBC_PostCondition:
    """post sub-key maps to icontract.ensure decorator, blame=implementer."""

    def test_post_parsed_into_spec(self):
        result = parse_dbc_behavior({"post": "result > 0"})
        assert result.spec["post"] == ["result > 0"]

    def test_post_blame_is_implementer(self):
        result = parse_dbc_behavior({"post": "result > 0"})
        assert result.blame["post"] == "implementer"

    def test_post_decorator_contains_ensure(self):
        result = parse_dbc_behavior({"post": "result > 0"})
        assert "ensure" in result.decorators

    def test_post_blame_not_caller(self):
        result = parse_dbc_behavior({"post": "result > 0"})
        assert result.blame.get("post") != "caller"


class TestParseDBC_Invariant:
    """inv sub-key maps to icontract.invariant decorator, blame=implementer."""

    def test_inv_parsed_into_spec(self):
        result = parse_dbc_behavior({"inv": "self.count >= 0"})
        assert result.spec["inv"] == ["self.count >= 0"]

    def test_inv_blame_is_implementer(self):
        result = parse_dbc_behavior({"inv": "self.ready"})
        assert result.blame["inv"] == "implementer"

    def test_inv_decorator_contains_invariant(self):
        result = parse_dbc_behavior({"inv": "self.ready"})
        assert "invariant" in result.decorators

    def test_inv_blame_not_caller(self):
        result = parse_dbc_behavior({"inv": "self.ready"})
        assert result.blame.get("inv") != "caller"


class TestParseDBC_Raises:
    """raises sub-key emits as comment, no blame entry."""

    def test_raises_parsed_into_spec(self):
        result = parse_dbc_behavior({"raises": "ValueError"})
        assert result.spec["raises"] == ["ValueError"]

    def test_raises_no_blame_entry(self):
        result = parse_dbc_behavior({"raises": "ValueError"})
        assert "raises" not in result.blame

    def test_raises_list_of_types(self):
        result = parse_dbc_behavior({"raises": ["ValueError", "TypeError"]})
        assert result.spec["raises"] == ["ValueError", "TypeError"]

    def test_raises_in_decorators(self):
        result = parse_dbc_behavior({"raises": "ValueError"})
        assert "ValueError" in result.decorators


class TestParseDBC_BehaviorKey:
    """The behavior key is accepted without error (it is not a contract clause)."""

    def test_behavior_key_ignored_spec_empty(self):
        result = parse_dbc_behavior({"behavior": "system returns OK"})
        assert result.spec == {"pre": [], "post": [], "inv": [], "raises": []}

    def test_behavior_key_no_blame(self):
        result = parse_dbc_behavior({"behavior": "system returns OK"})
        assert result.blame == {}


class TestParseDBC_InvalidInput:
    """Non-dict or unrecognised keys raise ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior("pre: x > 0")

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior(42)

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior(["pre", "x > 0"])

    def test_unknown_key_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior({"unknown_key": "value"})

    def test_typo_in_pre_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior({"pree": "x > 0"})

    def test_mixed_valid_invalid_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior({"pre": "x > 0", "bad_key": "oops"})


class TestParseDBC_SpecShape:
    """spec dict always has exactly four sub-keys."""

    def test_spec_has_four_keys(self):
        for ac in [{}, {"pre": "x > 0"}, {"raises": "E"}, {"post": "result > 0"}]:
            result = parse_dbc_behavior(ac)
            assert set(result.spec.keys()) == {"pre", "post", "inv", "raises"}

    def test_result_has_three_top_level_keys(self):
        result = parse_dbc_behavior({"pre": "x > 0"})
        assert set(vars(result).keys()) == {"spec", "decorators", "blame"}


class TestParseDBC_AllClauses:
    """All four sub-keys together produce complete spec and blame map."""

    def test_all_clauses_spec(self):
        result = parse_dbc_behavior(
            {"pre": "n >= 0", "post": "result >= 0", "inv": "self.ready", "raises": "E"}
        )
        assert result.spec["pre"] == ["n >= 0"]
        assert result.spec["post"] == ["result >= 0"]
        assert result.spec["inv"] == ["self.ready"]
        assert result.spec["raises"] == ["E"]

    def test_all_clauses_blame(self):
        result = parse_dbc_behavior(
            {"pre": "n >= 0", "post": "result >= 0", "inv": "self.ready"}
        )
        assert result.blame["pre"] == "caller"
        assert result.blame["post"] == "implementer"
        assert result.blame["inv"] == "implementer"
