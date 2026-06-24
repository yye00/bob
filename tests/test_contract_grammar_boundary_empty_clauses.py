"""Tests for boundary/edge cases — empty clauses, zero-clause Contract, etc."""

import pytest

from bob.spec_quality.contract_grammar import (
    parse_contract,
    parse_pre_clause,
    parse_post_clause,
    parse_inv_clause,
    parse_raises_clause,
    emit_icontract_decorators,
    ContractSpec,
    PreClause,
    PostClause,
    InvClause,
)


class TestParseContractEmptyDict:
    def test_parse_contract_empty_dict_returns_contract(self):
        result = parse_contract({})
        assert isinstance(result, ContractSpec)

    def test_parse_contract_empty_dict_has_zero_pre(self):
        result = parse_contract({})
        assert len(result.pre) == 0

    def test_parse_contract_empty_dict_has_zero_post(self):
        result = parse_contract({})
        assert len(result.post) == 0

    def test_parse_contract_empty_dict_has_zero_inv(self):
        result = parse_contract({})
        assert len(result.inv) == 0

    def test_parse_contract_empty_dict_has_zero_raises(self):
        result = parse_contract({})
        assert len(result.raises) == 0


class TestClauseParsersWithEmptyDict:
    def test_parse_pre_clause_empty_dict(self):
        result = parse_pre_clause({})
        assert isinstance(result, PreClause)
        assert result.expressions == []

    def test_parse_post_clause_empty_dict(self):
        result = parse_post_clause({})
        assert isinstance(result, PostClause)
        assert result.expressions == []

    def test_parse_inv_clause_empty_dict(self):
        result = parse_inv_clause({})
        assert isinstance(result, InvClause)
        assert result.expressions == []

    def test_parse_raises_clause_empty_dict(self):
        result = parse_raises_clause({})
        assert result == []


class TestClauseParsersWithNoneValues:
    def test_parse_pre_clause_none_value(self):
        result = parse_pre_clause({"pre": None})
        assert result.expressions == []

    def test_parse_post_clause_none_value(self):
        result = parse_post_clause({"post": None})
        assert result.expressions == []

    def test_parse_inv_clause_none_value(self):
        result = parse_inv_clause({"inv": None})
        assert result.expressions == []

    def test_parse_raises_clause_none_value(self):
        result = parse_raises_clause({"raises": None})
        assert result == []


class TestEmitWithEmptyClauses:
    def test_emit_empty_contract_returns_string(self):
        spec = ContractSpec()
        result = emit_icontract_decorators(spec)
        assert isinstance(result, str)

    def test_emit_empty_contract_returns_empty_or_blank(self):
        spec = ContractSpec()
        result = emit_icontract_decorators(spec)
        assert result == "" or result.strip() == ""


class TestClauseParsersReturnCorrectTypes:
    def test_parse_pre_clause_returns_pre_clause(self):
        result = parse_pre_clause({"pre": "x > 0"})
        assert isinstance(result, PreClause)

    def test_parse_post_clause_returns_post_clause(self):
        result = parse_post_clause({"post": "result > 0"})
        assert isinstance(result, PostClause)

    def test_parse_inv_clause_returns_inv_clause(self):
        result = parse_inv_clause({"inv": "self.ok"})
        assert isinstance(result, InvClause)

    def test_parse_raises_clause_returns_list(self):
        result = parse_raises_clause({"raises": ["ValueError"]})
        assert isinstance(result, list)
