"""Tests for the VerificationLevel enum."""

from bob.orchestrator.verification_level import VerificationLevel


class TestVerificationLevel:
    def test_values(self):
        assert VerificationLevel.UNIT.value == "unit"
        assert VerificationLevel.INTEGRATION.value == "integration"
        assert VerificationLevel.SYSTEM.value == "system"

    def test_infer_root(self):
        level = VerificationLevel.infer_from_depth(0, is_root=True)
        assert level == VerificationLevel.SYSTEM

    def test_infer_top_level_non_root(self):
        level = VerificationLevel.infer_from_depth(0, is_root=False)
        assert level == VerificationLevel.INTEGRATION

    def test_infer_deep(self):
        level = VerificationLevel.infer_from_depth(1)
        assert level == VerificationLevel.UNIT
        level = VerificationLevel.infer_from_depth(3)
        assert level == VerificationLevel.UNIT

    def test_string_enum(self):
        assert VerificationLevel("unit") == VerificationLevel.UNIT
        assert VerificationLevel("integration") == VerificationLevel.INTEGRATION
        assert VerificationLevel("system") == VerificationLevel.SYSTEM
