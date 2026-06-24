"""Tests for bob.behavior_ac_grammar.

Verifies the Design-by-Contract sub-grammar on EARS behavior: ACs.
The parse_dbc_behavior_ac function parses an EARS behavior AC dict
with optional pre/post/inv/raises sub-keys and returns structured
contract info including decorator code and blame assignments.
The codegen_icontract_decorators function generates icontract decorator
source strings from a ContractSpec.
"""

from __future__ import annotations

import pytest

from bob.behavior_ac_grammar import (
    parse_dbc_behavior_ac,
    codegen_icontract_decorators,
    ContractSpec,
)


class TestParseDatabaseAcBasic:
    """Basic correctness of parse_dbc_behavior_ac."""

    def test_returns_dict_with_expected_keys(self):
        result = parse_dbc_behavior_ac({"behavior": "returns result"})
        assert set(result.keys()) == {"spec", "decorators", "blame"}

    def test_empty_dict_returns_well_defined_result(self):
        result = parse_dbc_behavior_ac({})
        assert result["spec"] == {"pre": [], "post": [], "inv": [], "raises": []}
        assert result["decorators"] == ""
        assert result["blame"] == {}

    def test_pre_clause_parsed_and_blame_assigned(self):
        result = parse_dbc_behavior_ac({"pre": "x > 0"})
        assert result["spec"]["pre"] == ["x > 0"]
        assert result["blame"]["pre"] == "caller"
        assert "@icontract.require" in result["decorators"]

    def test_post_clause_parsed_and_blame_assigned(self):
        result = parse_dbc_behavior_ac({"post": "result > 0"})
        assert result["spec"]["post"] == ["result > 0"]
        assert result["blame"]["post"] == "implementer"
        assert "@icontract.ensure" in result["decorators"]

    def test_inv_clause_parsed_and_blame_assigned(self):
        result = parse_dbc_behavior_ac({"inv": "self.ready"})
        assert result["spec"]["inv"] == ["self.ready"]
        assert result["blame"]["inv"] == "implementer"
        assert "@icontract.invariant" in result["decorators"]

    def test_raises_clause_parsed(self):
        result = parse_dbc_behavior_ac({"raises": "ValueError"})
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
        result = parse_dbc_behavior_ac(ac)
        assert result["spec"]["pre"] == ["n >= 0"]
        assert result["spec"]["post"] == ["result >= 1"]
        assert result["spec"]["inv"] == ["self.ok"]
        assert result["spec"]["raises"] == ["OverflowError"]
        assert result["blame"]["pre"] == "caller"
        assert result["blame"]["post"] == "implementer"
        assert result["blame"]["inv"] == "implementer"

    def test_icontract_import_emitted_when_clauses_present(self):
        result = parse_dbc_behavior_ac({"pre": "x > 0"})
        assert "import icontract" in result["decorators"]

    def test_no_icontract_import_when_no_clauses(self):
        result = parse_dbc_behavior_ac({})
        assert "import icontract" not in result["decorators"]

    def test_pre_blame_is_caller(self):
        result = parse_dbc_behavior_ac({"pre": "n > 0"})
        assert result["blame"]["pre"] == "caller"

    def test_post_blame_is_implementer(self):
        result = parse_dbc_behavior_ac({"post": "result >= 0"})
        assert result["blame"]["post"] == "implementer"

    def test_inv_blame_is_implementer(self):
        result = parse_dbc_behavior_ac({"inv": "self.valid"})
        assert result["blame"]["inv"] == "implementer"

    def test_raises_not_in_blame(self):
        result = parse_dbc_behavior_ac({"raises": "TypeError"})
        assert "raises" not in result["blame"]

    def test_list_pre_clause(self):
        result = parse_dbc_behavior_ac({"pre": ["x > 0", "y > 0"]})
        assert result["spec"]["pre"] == ["x > 0", "y > 0"]

    def test_list_post_clause(self):
        result = parse_dbc_behavior_ac({"post": ["result > 0", "result < 100"]})
        assert result["spec"]["post"] == ["result > 0", "result < 100"]

    def test_list_raises_clause(self):
        result = parse_dbc_behavior_ac({"raises": ["ValueError", "TypeError"]})
        assert result["spec"]["raises"] == ["ValueError", "TypeError"]

    def test_behavior_key_not_in_spec(self):
        result = parse_dbc_behavior_ac({"behavior": "does something", "pre": "x > 0"})
        assert "behavior" not in result["spec"]


class TestParseDatabaseAcErrors:
    """Error handling in parse_dbc_behavior_ac."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior_ac(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior_ac("pre: x > 0")

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior_ac(["pre", "x > 0"])

    def test_unknown_key_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior_ac({"unknown_key": "value"})

    def test_mixed_valid_and_invalid_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dbc_behavior_ac({"pre": "x > 0", "bad_key": "oops"})


class TestCodegenIcontractDecorators:
    """Tests for codegen_icontract_decorators function."""

    def test_empty_spec_returns_empty_string(self):
        spec = ContractSpec()
        result = codegen_icontract_decorators(spec)
        assert result == ""

    def test_pre_clause_generates_require_decorator(self):
        spec = ContractSpec(pre=["x > 0"])
        result = codegen_icontract_decorators(spec)
        assert "@icontract.require" in result

    def test_post_clause_generates_ensure_decorator(self):
        spec = ContractSpec(post=["result > 0"])
        result = codegen_icontract_decorators(spec)
        assert "@icontract.ensure" in result

    def test_inv_clause_generates_invariant_decorator(self):
        spec = ContractSpec(inv=["self.ready"])
        result = codegen_icontract_decorators(spec)
        assert "@icontract.invariant" in result

    def test_raises_clause_generates_comment(self):
        spec = ContractSpec(raises=["ValueError"])
        result = codegen_icontract_decorators(spec)
        assert "ValueError" in result

    def test_import_icontract_included_when_clauses_present(self):
        spec = ContractSpec(pre=["x > 0"])
        result = codegen_icontract_decorators(spec)
        assert "import icontract" in result

    def test_no_import_when_no_clauses(self):
        spec = ContractSpec()
        result = codegen_icontract_decorators(spec)
        assert "import icontract" not in result

    def test_multiple_pre_clauses(self):
        spec = ContractSpec(pre=["x > 0", "y > 0"])
        result = codegen_icontract_decorators(spec)
        assert result.count("@icontract.require") == 2

    def test_all_clauses_combined(self):
        spec = ContractSpec(
            pre=["n >= 0"],
            post=["result >= 1"],
            inv=["self.ok"],
            raises=["OverflowError"],
        )
        result = codegen_icontract_decorators(spec)
        assert "@icontract.require" in result
        assert "@icontract.ensure" in result
        assert "@icontract.invariant" in result
        assert "OverflowError" in result
