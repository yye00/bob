"""Boundary tests for apply_design_by_contract.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions. Boundary cases include:
  - empty dict
  - dict with only the behavior key (no contract sub-keys)
  - None values for optional keys
  - empty-string clause values
  - single-item list vs bare string equivalence
  - raises-only with no other clauses
"""

from __future__ import annotations

import pytest

from f_r7_412.behavior_contract import apply_design_by_contract


class TestBoundaryEmptyAndMinimalInput:
    """Empty or minimal inputs return well-defined results, never raise."""

    def test_empty_dict_does_not_raise(self):
        result = apply_design_by_contract({})
        assert result is not None

    def test_empty_dict_spec_lists_are_empty(self):
        result = apply_design_by_contract({})
        for key in ("pre", "post", "inv", "raises"):
            assert result["spec"][key] == []

    def test_empty_dict_decorators_is_empty_string(self):
        result = apply_design_by_contract({})
        assert result["decorators"] == ""

    def test_empty_dict_blame_is_empty_dict(self):
        result = apply_design_by_contract({})
        assert result["blame"] == {}

    def test_behavior_key_only_no_contract_clauses(self):
        result = apply_design_by_contract(
            {"behavior": "parser returns BehaviorAC when AC matches grammar"}
        )
        assert result["spec"] == {"pre": [], "post": [], "inv": [], "raises": []}
        assert result["decorators"] == ""
        assert result["blame"] == {}

    def test_single_pre_clause_minimum_contract(self):
        result = apply_design_by_contract({"pre": "x > 0"})
        assert result["spec"]["pre"] == ["x > 0"]
        assert result["decorators"] != ""
        assert result["blame"] == {"pre": "caller"}

    def test_raises_only_no_decorators_except_comment(self):
        result = apply_design_by_contract({"raises": "ValueError"})
        assert result["spec"]["raises"] == ["ValueError"]
        assert "ValueError" in result["decorators"]
        assert result["blame"] == {}

    def test_single_item_list_equivalent_to_bare_string_pre(self):
        r1 = apply_design_by_contract({"pre": "x > 0"})
        r2 = apply_design_by_contract({"pre": ["x > 0"]})
        assert r1["spec"]["pre"] == r2["spec"]["pre"]

    def test_single_item_list_equivalent_to_bare_string_raises(self):
        r1 = apply_design_by_contract({"raises": "ValueError"})
        r2 = apply_design_by_contract({"raises": ["ValueError"]})
        assert r1["spec"]["raises"] == r2["spec"]["raises"]

    def test_result_always_has_three_top_level_keys(self):
        for ac in [{}, {"pre": "x > 0"}, {"raises": "E"}, {"post": "result > 0"}]:
            result = apply_design_by_contract(ac)
            assert set(result.keys()) == {"spec", "decorators", "blame"}

    def test_spec_always_has_four_sub_keys(self):
        for ac in [{}, {"pre": "x > 0"}, {"raises": "E"}]:
            result = apply_design_by_contract(ac)
            assert set(result["spec"].keys()) == {"pre", "post", "inv", "raises"}

    def test_multi_raises_list_boundary(self):
        result = apply_design_by_contract({"raises": ["ValueError", "TypeError"]})
        assert result["spec"]["raises"] == ["ValueError", "TypeError"]

    def test_all_clauses_present_boundary(self):
        result = apply_design_by_contract(
            {"pre": "n >= 0", "post": "result >= 0", "inv": "self.ready", "raises": "E"}
        )
        assert result["spec"]["pre"] == ["n >= 0"]
        assert result["spec"]["post"] == ["result >= 0"]
        assert result["spec"]["inv"] == ["self.ready"]
        assert result["spec"]["raises"] == ["E"]
