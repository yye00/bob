"""Tests for design_contract_sub_grammar_behavior_pre_post_inv_raises.

Verifies that the DbC sub-grammar facade correctly:
- Parses all four optional sub-keys (pre, post, inv, raises)
- Emits matching icontract decorators for codegen
- Applies blame assignment per Meyer's DbC rule
- Handles missing sub-keys gracefully
"""

from __future__ import annotations

import pytest

from bob3.design_contract_sub_grammar_behavior_pre_post_inv_raises import (
    design_contract_sub_grammar_behavior_pre_post_inv_raises,
)


def test_design_contract_sub_grammar_behavior_pre_post_inv_raises():
    """Core AC: function is callable and returns a non-empty result for a full contract."""
    ac = {
        "pre": "x > 0",
        "post": "result > 0",
        "inv": "self.valid",
        "raises": ["ValueError"],
    }
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result is not None
    # Result should include both the contract spec and decorator strings
    assert "spec" in result
    assert "decorators" in result
    assert "blame" in result


def test_parse_pre_condition():
    """Pre-conditions are parsed and emitted as icontract.require decorators."""
    ac = {"pre": "x > 0"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert "icontract.require" in result["decorators"]
    assert "x" in result["decorators"]


def test_parse_post_condition():
    """Post-conditions are parsed and emitted as icontract.ensure decorators."""
    ac = {"post": "result > 0"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert "icontract.ensure" in result["decorators"]
    assert "result" in result["decorators"]


def test_parse_invariant():
    """Invariants are parsed and emitted as icontract.invariant decorators."""
    ac = {"inv": "self.count >= 0"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert "icontract.invariant" in result["decorators"]


def test_parse_raises():
    """Declared exception types appear as structured comments in the decorator output."""
    ac = {"raises": ["ValueError", "TypeError"]}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert "ValueError" in result["decorators"]
    assert "TypeError" in result["decorators"]


def test_blame_pre_violation_charges_caller():
    """Pre-condition violations charge the caller (not the implementer)."""
    ac = {"pre": "x > 0"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result["blame"]["pre"] == "caller"


def test_blame_post_violation_charges_implementer():
    """Post-condition violations charge the implementer."""
    ac = {"post": "result >= 0"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result["blame"]["post"] == "implementer"


def test_blame_inv_violation_charges_implementer():
    """Invariant violations charge the implementer."""
    ac = {"inv": "self.valid"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result["blame"]["inv"] == "implementer"


def test_empty_ac_returns_empty_decorators():
    """An AC dict with no contract sub-keys produces empty decorator output."""
    ac = {}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result["decorators"] == ""


def test_behavior_key_ignored():
    """The EARS 'behavior' key is accepted without raising."""
    ac = {"behavior": "WHEN the user submits THEN result is returned", "pre": "n > 0"}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result is not None
    assert "icontract.require" in result["decorators"]


def test_full_contract_all_four_keys():
    """All four sub-keys together produce a complete decorator stack."""
    ac = {
        "pre": ["x > 0", "y > 0"],
        "post": "result > 0",
        "inv": "self.total >= 0",
        "raises": ["OverflowError"],
    }
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert "icontract.require" in result["decorators"]
    assert "icontract.ensure" in result["decorators"]
    assert "icontract.invariant" in result["decorators"]
    assert "OverflowError" in result["decorators"]


def test_multiple_pre_conditions():
    """Multiple pre-conditions each produce a separate require decorator."""
    ac = {"pre": ["a > 0", "b > 0"]}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    assert result["decorators"].count("icontract.require") == 2


def test_spec_contains_parsed_clauses():
    """The spec field in the result reflects the parsed contract clauses."""
    ac = {"pre": "x > 0", "raises": ["ValueError"]}
    result = design_contract_sub_grammar_behavior_pre_post_inv_raises(ac)
    spec = result["spec"]
    assert "x > 0" in spec["pre"]
    assert "ValueError" in spec["raises"]
