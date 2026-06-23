"""Tests for blame attribution — pre violations charge caller, post violations charge implementer."""

import pytest
import icontract

from bob3.spec_quality.contract_grammar import (
    parse_contract,
    emit_icontract_decorators,
    attribute_blame,
    ContractSpec,
    BlameTarget,
)


class TestBlameAttributionModel:
    def test_blame_target_has_caller_and_implementer(self):
        assert hasattr(BlameTarget, "CALLER")
        assert hasattr(BlameTarget, "IMPLEMENTER")

    def test_pre_violation_blames_caller(self):
        blame = attribute_blame(violation_type="pre")
        assert blame == BlameTarget.CALLER

    def test_post_violation_blames_implementer(self):
        blame = attribute_blame(violation_type="post")
        assert blame == BlameTarget.IMPLEMENTER

    def test_inv_violation_blames_implementer(self):
        blame = attribute_blame(violation_type="inv")
        assert blame == BlameTarget.IMPLEMENTER

    def test_unknown_violation_type_raises(self):
        with pytest.raises((ValueError, KeyError)):
            attribute_blame(violation_type="unknown_type")


class TestBlameWithContractSpec:
    def test_pre_violation_in_contract_spec_blames_caller(self):
        spec = ContractSpec(pre=["x > 0"], post=[], inv=[], raises=[])
        blame = attribute_blame(violation_type="pre", spec=spec)
        assert blame == BlameTarget.CALLER

    def test_post_violation_in_contract_spec_blames_implementer(self):
        spec = ContractSpec(pre=[], post=["result > 0"], inv=[], raises=[])
        blame = attribute_blame(violation_type="post", spec=spec)
        assert blame == BlameTarget.IMPLEMENTER


class TestBlameReport:
    def test_attribute_blame_returns_blame_target(self):
        result = attribute_blame(violation_type="pre")
        assert isinstance(result, BlameTarget)

    def test_caller_blame_string_representation(self):
        blame = attribute_blame(violation_type="pre")
        blame_str = str(blame)
        assert "CALLER" in blame_str or "caller" in blame_str.lower()

    def test_implementer_blame_string_representation(self):
        blame = attribute_blame(violation_type="post")
        blame_str = str(blame)
        assert "IMPLEMENTER" in blame_str or "implementer" in blame_str.lower()


class TestBlameIntegration:
    """Verify mechanical blame assignment matches Meyer's Design-by-Contract rule."""

    def test_pre_fires_before_function_body(self):
        """Pre conditions must fire before function body executes."""

        @icontract.require(lambda x: x > 0)
        def my_func(x):
            return x * 2

        with pytest.raises(icontract.ViolationError):
            my_func(-1)
        # If pre fires, blame is CALLER (they passed invalid -1)
        blame = attribute_blame(violation_type="pre")
        assert blame == BlameTarget.CALLER

    def test_post_fires_after_function_body(self):
        """Post conditions fire after function body executes."""

        @icontract.ensure(lambda result: result > 0)
        def buggy_func(x):
            return -abs(x)  # always negative — implementer bug

        with pytest.raises(icontract.ViolationError):
            buggy_func(5)
        # If post fires, blame is IMPLEMENTER (they returned wrong value)
        blame = attribute_blame(violation_type="post")
        assert blame == BlameTarget.IMPLEMENTER

    def test_parse_and_emit_and_blame_pipeline(self):
        """Full pipeline: parse -> emit -> attribute blame."""
        ac = {
            "pre": "n > 0",
            "post": "result > 0",
        }
        spec = parse_contract(ac)
        code = emit_icontract_decorators(spec)

        assert "@icontract.require" in code
        assert "@icontract.ensure" in code

        pre_blame = attribute_blame(violation_type="pre", spec=spec)
        post_blame = attribute_blame(violation_type="post", spec=spec)

        assert pre_blame == BlameTarget.CALLER
        assert post_blame == BlameTarget.IMPLEMENTER
