"""Tests for parse_contract — pre/post/inv/raises parsing from behavior: AC YAML."""

import pytest

from bob.spec_quality.contract_grammar import parse_contract, ContractSpec


class TestParsePre:
    def test_parses_simple_pre(self):
        ac = {"pre": "x > 0"}
        result = parse_contract(ac)
        assert isinstance(result, ContractSpec)
        assert result.pre == ["x > 0"]

    def test_parses_pre_list(self):
        ac = {"pre": ["x > 0", "y is not None"]}
        result = parse_contract(ac)
        assert result.pre == ["x > 0", "y is not None"]

    def test_pre_empty_when_absent(self):
        ac = {"post": "result > 0"}
        result = parse_contract(ac)
        assert result.pre == []


class TestParsePost:
    def test_parses_simple_post(self):
        ac = {"post": "result >= 0"}
        result = parse_contract(ac)
        assert result.post == ["result >= 0"]

    def test_parses_post_list(self):
        ac = {"post": ["result >= 0", "len(result) > 0"]}
        result = parse_contract(ac)
        assert result.post == ["result >= 0", "len(result) > 0"]

    def test_post_empty_when_absent(self):
        ac = {"pre": "x > 0"}
        result = parse_contract(ac)
        assert result.post == []


class TestParseInv:
    def test_parses_single_inv(self):
        ac = {"inv": "self.count >= 0"}
        result = parse_contract(ac)
        assert result.inv == ["self.count >= 0"]

    def test_parses_inv_list(self):
        ac = {"inv": ["self.count >= 0", "self.name != ''"]}
        result = parse_contract(ac)
        assert result.inv == ["self.count >= 0", "self.name != ''"]

    def test_inv_empty_when_absent(self):
        ac = {}
        result = parse_contract(ac)
        assert result.inv == []


class TestParseRaises:
    def test_parses_single_raises(self):
        ac = {"raises": "ValueError"}
        result = parse_contract(ac)
        assert result.raises == ["ValueError"]

    def test_parses_raises_list(self):
        ac = {"raises": ["ValueError", "TypeError"]}
        result = parse_contract(ac)
        assert result.raises == ["ValueError", "TypeError"]

    def test_raises_empty_when_absent(self):
        ac = {}
        result = parse_contract(ac)
        assert result.raises == []


class TestParseAll:
    def test_full_contract(self):
        ac = {
            "pre": "n > 0",
            "post": "result > 0",
            "inv": "self.initialized",
            "raises": "ValueError",
        }
        result = parse_contract(ac)
        assert result.pre == ["n > 0"]
        assert result.post == ["result > 0"]
        assert result.inv == ["self.initialized"]
        assert result.raises == ["ValueError"]

    def test_empty_dict_gives_empty_contract(self):
        result = parse_contract({})
        assert result.pre == []
        assert result.post == []
        assert result.inv == []
        assert result.raises == []

    def test_none_values_are_treated_as_absent(self):
        ac = {"pre": None, "post": None, "inv": None, "raises": None}
        result = parse_contract(ac)
        assert result.pre == []
        assert result.post == []
        assert result.inv == []
        assert result.raises == []

    def test_string_pre_normalized_to_list(self):
        ac = {"pre": "x > 0"}
        result = parse_contract(ac)
        assert isinstance(result.pre, list)
        assert len(result.pre) == 1


class TestParseFromBehaviorAC:
    """parse_contract can also accept a behavior: AC string with embedded YAML-like sub-keys."""

    def test_parses_from_behavior_dict_sub_keys(self):
        """Full behavior: AC dict representation with sub-keys."""
        ac = {
            "behavior": "parser returns ContractSpec when given pre/post",
            "pre": "ac is dict",
            "post": "isinstance(result, ContractSpec)",
        }
        result = parse_contract(ac)
        assert result.pre == ["ac is dict"]
        assert result.post == ["isinstance(result, ContractSpec)"]
