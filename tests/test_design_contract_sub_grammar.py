"""Tests for bob.design_contract_sub_grammar.

Covers the canonical Design-by-Contract sub-grammar entry points:

    parse_behavior_contract  — parse + validate a behavior AC dict
    emit_icontract_decorators — emit icontract decorator source

and the integration with bob.behavior_ac_verifier.
"""

from __future__ import annotations

import pathlib

import pytest

from bob.design_contract_sub_grammar import (
    emit_icontract_decorators,
    parse_behavior_contract,
)


class TestParseBehaviorContractBasic:
    """Structured parse of behavior AC dicts."""

    def test_empty_dict_returns_empty_spec(self):
        result = parse_behavior_contract({})
        assert result["spec"] == {"pre": [], "post": [], "inv": [], "raises": []}
        assert result["blame"] == {}
        assert result["has_contract"] is False

    def test_behavior_key_only_no_contract(self):
        result = parse_behavior_contract({"behavior": "returns a BehaviorAC"})
        assert result["has_contract"] is False
        assert result["blame"] == {}

    def test_pre_clause_bare_string(self):
        result = parse_behavior_contract({"pre": "x > 0"})
        assert result["spec"]["pre"] == ["x > 0"]
        assert result["has_contract"] is True

    def test_pre_clause_list(self):
        result = parse_behavior_contract({"pre": ["x > 0", "y < 10"]})
        assert result["spec"]["pre"] == ["x > 0", "y < 10"]

    def test_all_clauses_present(self):
        result = parse_behavior_contract(
            {"pre": "n >= 0", "post": "result >= 0", "inv": "self.ready",
             "raises": ["ValueError", "TypeError"]}
        )
        assert result["spec"]["pre"] == ["n >= 0"]
        assert result["spec"]["post"] == ["result >= 0"]
        assert result["spec"]["inv"] == ["self.ready"]
        assert result["spec"]["raises"] == ["ValueError", "TypeError"]
        assert result["has_contract"] is True


class TestParseBehaviorContractBlame:
    """Meyer's DbC blame rule: pre → caller, post/inv → implementer."""

    def test_pre_blames_caller(self):
        result = parse_behavior_contract({"pre": "x > 0"})
        assert result["blame"] == {"pre": "caller"}

    def test_post_blames_implementer(self):
        result = parse_behavior_contract({"post": "result > 0"})
        assert result["blame"] == {"post": "implementer"}

    def test_inv_blames_implementer(self):
        result = parse_behavior_contract({"inv": "self.ok"})
        assert result["blame"] == {"inv": "implementer"}

    def test_raises_not_in_blame_map(self):
        result = parse_behavior_contract({"raises": "ValueError"})
        assert result["blame"] == {}

    def test_pre_and_post_distinct_blame(self):
        result = parse_behavior_contract({"pre": "x > 0", "post": "result > 0"})
        assert result["blame"] == {"pre": "caller", "post": "implementer"}


class TestParseBehaviorContractErrors:
    """Invalid input raises ValueError, never silently succeeds."""

    @pytest.mark.parametrize("bad", [None, "pre: x", 42, ["pre"], ("pre",)])
    def test_non_dict_raises_value_error(self, bad):
        with pytest.raises(ValueError):
            parse_behavior_contract(bad)

    def test_unrecognised_key_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_behavior_contract({"unknown_key": "value"})

    def test_typo_key_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_behavior_contract({"pree": "x > 0"})


class TestEmitIcontractDecorators:
    """Decorator source emission."""

    def test_empty_contract_emits_empty_string(self):
        assert emit_icontract_decorators({}) == ""

    def test_pre_emits_require(self):
        src = emit_icontract_decorators({"pre": "x > 0"})
        assert "import icontract" in src
        assert "@icontract.require" in src

    def test_post_emits_ensure(self):
        src = emit_icontract_decorators({"post": "result > 0"})
        assert "@icontract.ensure" in src

    def test_inv_emits_invariant(self):
        src = emit_icontract_decorators({"inv": "self.ok"})
        assert "@icontract.invariant" in src

    def test_raises_emits_comment(self):
        src = emit_icontract_decorators({"raises": ["ValueError"]})
        assert "ValueError" in src

    def test_accepts_parse_result_via_spec_key(self):
        parsed = parse_behavior_contract({"pre": "x > 0"})
        src = emit_icontract_decorators(parsed)
        assert "@icontract.require" in src

    def test_non_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_icontract_decorators("pre: x > 0")

    def test_raw_dict_unrecognised_key_raises(self):
        with pytest.raises(ValueError):
            emit_icontract_decorators({"bogus": "x"})


class TestIntegrationBehaviorAcVerifier:
    """Integration with bob.behavior_ac_verifier.

    The contract sub-grammar and the quoted-substring verifier both operate
    on behavior ACs; this exercises them together on a shared workspace.
    """

    def test_verifier_importable_and_callable(self):
        from bob.behavior_ac_verifier import verify_quoted_substring_ac

        # A behavior criterion with no quoted literals -> None (fall through).
        result = verify_quoted_substring_ac(
            "behavior: parser returns a contract", pathlib.Path(".")
        )
        assert result is None

    def test_contract_and_verifier_share_behavior_ac(self, tmp_path):
        from bob.behavior_ac_verifier import verify_quoted_substring_ac

        # Contract parse yields blame; verifier scans the workspace.
        contract = parse_behavior_contract({"pre": "x > 0", "behavior": "check"})
        assert contract["blame"] == {"pre": "caller"}

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "mod.py").write_text("MARKER = 'icontract'\n")
        criterion = "behavior: source MUST mention 'icontract'"
        assert verify_quoted_substring_ac(criterion, tmp_path) is True
