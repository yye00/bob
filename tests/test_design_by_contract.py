"""Tests for f_r7_412.design_by_contract.behavior_with_contract.

Verifies the Design-by-Contract sub-grammar on EARS behavior: ACs.
The behavior_with_contract function parses an EARS behavior AC dict
with optional pre/post/inv/raises sub-keys and returns structured
contract info including decorator code and blame assignments.
"""

from __future__ import annotations

import pytest

from f_r7_412.design_by_contract import behavior_with_contract


class TestBehaviorWithContractBasic:
    """Basic correctness of behavior_with_contract."""

    def test_returns_dict_with_expected_keys(self):
        result = behavior_with_contract({"behavior": "returns result"})
        assert set(result.keys()) == {"behavior", "spec", "decorators", "blame"}

    def test_behavior_key_preserved(self):
        result = behavior_with_contract({"behavior": "parser returns BehaviorAC"})
        assert result["behavior"] == "parser returns BehaviorAC"

    def test_empty_dict_returns_well_defined_result(self):
        result = behavior_with_contract({})
        assert result["behavior"] == ""
        assert result["spec"] == {"pre": [], "post": [], "inv": [], "raises": []}
        assert result["decorators"] == ""
        assert result["blame"] == {}

    def test_pre_clause_parsed_and_blame_assigned(self):
        result = behavior_with_contract({"behavior": "validates input", "pre": "x > 0"})
        assert result["spec"]["pre"] == ["x > 0"]
        assert result["blame"]["pre"] == "caller"
        assert "@icontract.require" in result["decorators"]

    def test_post_clause_parsed_and_blame_assigned(self):
        result = behavior_with_contract({"behavior": "returns positive", "post": "result > 0"})
        assert result["spec"]["post"] == ["result > 0"]
        assert result["blame"]["post"] == "implementer"
        assert "@icontract.ensure" in result["decorators"]

    def test_inv_clause_parsed_and_blame_assigned(self):
        result = behavior_with_contract({"behavior": "maintains state", "inv": "self.ready"})
        assert result["spec"]["inv"] == ["self.ready"]
        assert result["blame"]["inv"] == "implementer"
        assert "@icontract.invariant" in result["decorators"]

    def test_raises_clause_parsed(self):
        result = behavior_with_contract({"raises": "ValueError"})
        assert result["spec"]["raises"] == ["ValueError"]
        assert "ValueError" in result["decorators"]

    def test_all_clauses_together(self):
        ac = {
            "behavior": "computes factorial",
            "pre": "n >= 0",
            "post": "result >= 1",
            "inv": "self.ok",
            "raises": "OverflowError",
        }
        result = behavior_with_contract(ac)
        assert result["spec"]["pre"] == ["n >= 0"]
        assert result["spec"]["post"] == ["result >= 1"]
        assert result["spec"]["inv"] == ["self.ok"]
        assert result["spec"]["raises"] == ["OverflowError"]
        assert result["blame"]["pre"] == "caller"
        assert result["blame"]["post"] == "implementer"
        assert result["blame"]["inv"] == "implementer"

    def test_icontract_import_emitted_when_clauses_present(self):
        result = behavior_with_contract({"pre": "x > 0"})
        assert "import icontract" in result["decorators"]

    def test_no_icontract_import_when_no_clauses(self):
        result = behavior_with_contract({})
        assert "import icontract" not in result["decorators"]

    def test_multi_pre_clauses_list(self):
        result = behavior_with_contract({"pre": ["x > 0", "y > 0"]})
        assert result["spec"]["pre"] == ["x > 0", "y > 0"]
        assert result["blame"]["pre"] == "caller"

    def test_multi_raises_list(self):
        result = behavior_with_contract({"raises": ["ValueError", "TypeError"]})
        assert result["spec"]["raises"] == ["ValueError", "TypeError"]

    def test_pre_violation_charges_caller(self):
        result = behavior_with_contract({"pre": "n > 0"})
        assert result["blame"].get("pre") == "caller"

    def test_post_violation_charges_implementer(self):
        result = behavior_with_contract({"post": "result is not None"})
        assert result["blame"].get("post") == "implementer"

    def test_inv_violation_charges_implementer(self):
        result = behavior_with_contract({"inv": "self.count >= 0"})
        assert result["blame"].get("inv") == "implementer"


class TestBehaviorWithContractErrors:
    """Invalid input raises ValueError."""

    def test_non_dict_input_raises_value_error(self):
        with pytest.raises(ValueError):
            behavior_with_contract(None)

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError):
            behavior_with_contract("pre: x > 0")

    def test_list_input_raises_value_error(self):
        with pytest.raises(ValueError):
            behavior_with_contract(["pre", "x > 0"])

    def test_unknown_key_raises_value_error(self):
        with pytest.raises(ValueError):
            behavior_with_contract({"unknown_key": "value"})

    def test_typo_key_raises_value_error(self):
        with pytest.raises(ValueError):
            behavior_with_contract({"pree": "x > 0"})
