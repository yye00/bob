"""Tests for raises_on_malformed_clause — rejects unknown sub-keys with ContractParseError."""

import pytest

from bob.spec_quality.contract_grammar import (
    ContractParseError,
    raises_on_malformed_clause,
)


class TestRejectsMalformedKeys:
    def test_raises_on_unknown_key(self):
        with pytest.raises(ContractParseError):
            raises_on_malformed_clause({"unknown_key": "value"})

    def test_raises_on_multiple_unknown_keys(self):
        with pytest.raises(ContractParseError):
            raises_on_malformed_clause({"foo": "bar", "baz": "qux"})

    def test_raises_on_typo_in_key(self):
        with pytest.raises(ContractParseError):
            raises_on_malformed_clause({"precondition": "x > 0"})

    def test_raises_on_mixed_known_and_unknown_keys(self):
        with pytest.raises(ContractParseError):
            raises_on_malformed_clause({"pre": "x > 0", "invalid": "junk"})

    def test_error_message_contains_bad_key(self):
        with pytest.raises(ContractParseError, match="mystery_key"):
            raises_on_malformed_clause({"mystery_key": "value"})


class TestAcceptsValidKeys:
    def test_accepts_pre_only(self):
        raises_on_malformed_clause({"pre": "x > 0"})

    def test_accepts_post_only(self):
        raises_on_malformed_clause({"post": "result > 0"})

    def test_accepts_inv_only(self):
        raises_on_malformed_clause({"inv": "self.ok"})

    def test_accepts_raises_only(self):
        raises_on_malformed_clause({"raises": "ValueError"})

    def test_accepts_behavior_key(self):
        raises_on_malformed_clause({"behavior": "parser returns X when Y"})

    def test_accepts_all_known_keys(self):
        raises_on_malformed_clause({
            "behavior": "f does g when h",
            "pre": "x > 0",
            "post": "result > 0",
            "inv": "self.ok",
            "raises": ["ValueError"],
        })

    def test_accepts_empty_dict(self):
        raises_on_malformed_clause({})


class TestContractParseErrorIsValueError:
    def test_contract_parse_error_is_value_error(self):
        with pytest.raises(ValueError):
            raises_on_malformed_clause({"bad": "key"})
