"""Tests for bob3.spec_extractor.reject_behavior_ac_for_verifier_extension.

Verifies the AC discipline rule: verifier-extension features MUST express
ACs as structural + integration pytest only (no behavior ACs).

The reject_behavior_ac_for_verifier_extension function enforces this at
spec-extraction time by rejecting any AC line starting with 'behavior:'
when the feature's primary diff target is a VERIFIER_EXTENSION_MODULES path.
"""

from __future__ import annotations

import pytest

from bob3.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    reject_behavior_ac_for_verifier_extension,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_normal_module.py"


class TestRejectBehaviorAcForVerifierExtension:
    """Tests for reject_behavior_ac_for_verifier_extension."""

    def test_behavior_ac_rejected_for_verifier_extension(self):
        """Behavior ACs are rejected when primary_diff_target is a verifier module."""
        acs = ["behavior: output MUST contain X"]
        result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert result.is_verifier_extension is True
        assert len(result.demoted) == 1
        assert result.demoted[0].original == "behavior: output MUST contain X"
        assert "[SKIP" in result.filtered_acs[0]

    def test_structural_ac_passes_for_verifier_extension(self):
        """Structural ACs pass through for verifier-extension features."""
        acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
        result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert result.filtered_acs == acs
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_integration_ac_passes_for_verifier_extension(self):
        """Integration pytest ACs pass through for verifier-extension features."""
        acs = ["integration: pytest tests/test_foo.py::test_bar passes"]
        result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert result.filtered_acs == acs
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_pytest_ac_passes_for_verifier_extension(self):
        """Pytest ACs pass through for verifier-extension features."""
        acs = ["pytest: tests/test_foo.py::test_bar"]
        result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert result.filtered_acs == acs
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_normal_feature_unchanged(self):
        """Behavior ACs are NOT rejected for non-verifier-extension features."""
        acs = ["behavior: the API returns 200 status"]
        result = reject_behavior_ac_for_verifier_extension(acs, _NORMAL_TARGET)
        assert result.is_verifier_extension is False
        assert result.filtered_acs == acs
        assert result.demoted == []

    def test_multiple_acs_partial_demotion(self):
        """Only behavior ACs are demoted; structural/pytest ACs survive unchanged."""
        acs = [
            "File exists: src/bob3/enhanced_verification.py",
            "behavior: MUST NOT crash",
            "pytest: tests/test_enhanced_verification.py",
            "behavior: output MUST include summary",
        ]
        result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert result.is_verifier_extension is True
        assert len(result.demoted) == 2
        assert len(result.filtered_acs) == 4
        # Non-behavior ACs preserved verbatim
        assert result.filtered_acs[0] == acs[0]
        assert result.filtered_acs[2] == acs[2]
        # Behavior ACs replaced with skip notes
        assert "[SKIP" in result.filtered_acs[1]
        assert "[SKIP" in result.filtered_acs[3]

    def test_non_list_acs_raises_value_error(self):
        """Passing a non-list raises ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            reject_behavior_ac_for_verifier_extension("not a list", _VERIFIER_TARGET)

    def test_none_acs_raises_value_error(self):
        """Passing None raises ValueError."""
        with pytest.raises(ValueError):
            reject_behavior_ac_for_verifier_extension(None, _VERIFIER_TARGET)

    def test_tuple_acs_raises_value_error(self):
        """Passing a tuple raises ValueError."""
        with pytest.raises(ValueError):
            reject_behavior_ac_for_verifier_extension(("behavior: test",), _VERIFIER_TARGET)

    def test_empty_acs_returns_empty_filtered(self):
        """Empty AC list returns empty filtered_acs and no demotions."""
        result = reject_behavior_ac_for_verifier_extension([], _VERIFIER_TARGET)
        assert result.filtered_acs == []
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_returns_acfilterresult_instance(self):
        """Return type is ACFilterResult."""
        result = reject_behavior_ac_for_verifier_extension([], _VERIFIER_TARGET)
        assert isinstance(result, ACFilterResult)

    def test_feature_id_kwarg_accepted(self):
        """feature_id keyword argument is accepted without error."""
        result = reject_behavior_ac_for_verifier_extension(
            ["behavior: something"],
            _VERIFIER_TARGET,
            feature_id="test-feature-123",
        )
        assert result.is_verifier_extension is True
        assert len(result.demoted) == 1

    def test_all_verifier_extension_modules_trigger_rule(self):
        """Every module in VERIFIER_EXTENSION_MODULES triggers the discipline rule."""
        assert len(VERIFIER_EXTENSION_MODULES) > 0
        for module_path in VERIFIER_EXTENSION_MODULES:
            acs = ["behavior: some verifier behavior"]
            result = reject_behavior_ac_for_verifier_extension(acs, module_path)
            assert result.is_verifier_extension is True, (
                f"Module {module_path!r} should trigger verifier-extension rule"
            )
            assert len(result.demoted) == 1


class TestIntegrationWithOrchestrator:
    """Integration tests verifying bob3.spec_extractor works with orchestrator context."""

    def test_same_verifier_extension_modules_as_spec_quality(self):
        """bob3.spec_extractor re-exports the same VERIFIER_EXTENSION_MODULES as spec_quality."""
        from bob3.spec_quality.spec_extractor import (
            VERIFIER_EXTENSION_MODULES as spec_quality_modules,
        )
        assert VERIFIER_EXTENSION_MODULES == spec_quality_modules

    def test_reject_function_delegates_to_filter_behavior(self):
        """reject_behavior_ac_for_verifier_extension delegates to filter_behavior_acs_for_verifier_extension."""
        from bob3.spec_quality.spec_extractor import filter_behavior_acs_for_verifier_extension

        acs = ["behavior: some behavior", "File exists: foo.py"]
        result_reject = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        result_filter = filter_behavior_acs_for_verifier_extension(acs, _VERIFIER_TARGET)

        assert result_reject.is_verifier_extension == result_filter.is_verifier_extension
        assert result_reject.filtered_acs == result_filter.filtered_acs
        assert len(result_reject.demoted) == len(result_filter.demoted)
