"""Tests for f_r7_412.behavior_contract.apply_design_by_contract.

Covers the Design-by-Contract sub-grammar on EARS behavior: ACs:
  - pre / post / inv / raises clause parsing
  - icontract decorator emission
  - blame attribution (pre→caller, post/inv→implementer)
  - single-string and list-of-string clause inputs
  - empty dict (no-op) path
"""

from __future__ import annotations

import pytest

from f_r7_412.behavior_contract import apply_design_by_contract


class TestApplyDesignByContractSpec:
    """Clause parsing into spec dict."""

    def test_empty_dict_returns_empty_spec(self):
        result = apply_design_by_contract({})
        assert result["spec"] == {"pre": [], "post": [], "inv": [], "raises": []}

    def test_pre_string_normalised_to_list(self):
        result = apply_design_by_contract({"pre": "x > 0"})
        assert result["spec"]["pre"] == ["x > 0"]

    def test_post_string_normalised_to_list(self):
        result = apply_design_by_contract({"post": "result >= 0"})
        assert result["spec"]["post"] == ["result >= 0"]

    def test_inv_string_normalised_to_list(self):
        result = apply_design_by_contract({"inv": "self.count >= 0"})
        assert result["spec"]["inv"] == ["self.count >= 0"]

    def test_raises_string_normalised_to_list(self):
        result = apply_design_by_contract({"raises": "ValueError"})
        assert result["spec"]["raises"] == ["ValueError"]

    def test_pre_list_preserved(self):
        result = apply_design_by_contract({"pre": ["x > 0", "y < 100"]})
        assert result["spec"]["pre"] == ["x > 0", "y < 100"]

    def test_raises_list_preserved(self):
        result = apply_design_by_contract({"raises": ["ValueError", "TypeError"]})
        assert result["spec"]["raises"] == ["ValueError", "TypeError"]

    def test_behavior_key_silently_ignored(self):
        result = apply_design_by_contract(
            {"behavior": "parser returns BehaviorAC when AC matches grammar", "pre": "x > 0"}
        )
        assert result["spec"]["pre"] == ["x > 0"]

    def test_all_clauses_together(self):
        result = apply_design_by_contract(
            {"pre": "n > 0", "post": "result > 0", "inv": "self.ok", "raises": "ValueError"}
        )
        spec = result["spec"]
        assert spec["pre"] == ["n > 0"]
        assert spec["post"] == ["result > 0"]
        assert spec["inv"] == ["self.ok"]
        assert spec["raises"] == ["ValueError"]


class TestApplyDesignByContractDecorators:
    """icontract decorator emission."""

    def test_empty_dict_emits_no_decorators(self):
        result = apply_design_by_contract({})
        assert result["decorators"] == ""

    def test_pre_emits_require_decorator(self):
        result = apply_design_by_contract({"pre": "x > 0"})
        assert "@icontract.require" in result["decorators"]
        assert "x > 0" in result["decorators"]

    def test_post_emits_ensure_decorator(self):
        result = apply_design_by_contract({"post": "result >= 0"})
        assert "@icontract.ensure" in result["decorators"]
        assert "result >= 0" in result["decorators"]

    def test_inv_emits_invariant_decorator(self):
        result = apply_design_by_contract({"inv": "self.count >= 0"})
        assert "@icontract.invariant" in result["decorators"]
        assert "self.count >= 0" in result["decorators"]

    def test_raises_emits_comment(self):
        result = apply_design_by_contract({"raises": "ValueError"})
        assert "# raises:" in result["decorators"]
        assert "ValueError" in result["decorators"]

    def test_import_icontract_present_when_clauses_exist(self):
        result = apply_design_by_contract({"pre": "x > 0"})
        assert "import icontract" in result["decorators"]

    def test_decorators_is_string(self):
        result = apply_design_by_contract({"pre": "x > 0"})
        assert isinstance(result["decorators"], str)


class TestApplyDesignByContractBlame:
    """Blame attribution per Meyer's DbC rule."""

    def test_pre_blames_caller(self):
        result = apply_design_by_contract({"pre": "x > 0"})
        assert result["blame"]["pre"] == "caller"

    def test_post_blames_implementer(self):
        result = apply_design_by_contract({"post": "result >= 0"})
        assert result["blame"]["post"] == "implementer"

    def test_inv_blames_implementer(self):
        result = apply_design_by_contract({"inv": "self.ok"})
        assert result["blame"]["inv"] == "implementer"

    def test_empty_dict_produces_empty_blame(self):
        result = apply_design_by_contract({})
        assert result["blame"] == {}

    def test_raises_only_does_not_add_to_blame(self):
        result = apply_design_by_contract({"raises": "ValueError"})
        assert "raises" not in result["blame"]

    def test_full_spec_blame_keys(self):
        result = apply_design_by_contract(
            {"pre": "n > 0", "post": "result > 0", "inv": "self.ok"}
        )
        assert result["blame"] == {
            "pre": "caller",
            "post": "implementer",
            "inv": "implementer",
        }


class TestApplyDesignByContractReturnShape:
    """Return value always has exactly the three expected keys."""

    def test_result_has_spec_key(self):
        result = apply_design_by_contract({})
        assert "spec" in result

    def test_result_has_decorators_key(self):
        result = apply_design_by_contract({})
        assert "decorators" in result

    def test_result_has_blame_key(self):
        result = apply_design_by_contract({})
        assert "blame" in result

    def test_spec_has_all_four_sub_keys(self):
        result = apply_design_by_contract({})
        spec = result["spec"]
        assert set(spec.keys()) == {"pre", "post", "inv", "raises"}
