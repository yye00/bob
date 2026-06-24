"""Tests for verifier.spec_extractor.reject_behavior_acs_for_extensions.

Verifies the AC discipline rule: verifier-extension features MUST express
ACs as structural + integration pytest only (no behavior ACs).

The reject_behavior_acs_for_extensions function enforces this at spec-extraction
time by rejecting any AC line starting with 'behavior:' when the feature's
primary diff target is a VERIFIER_EXTENSION_MODULES path.
"""

from __future__ import annotations

import pytest

from verifier.spec_extractor import (
    VERIFIER_EXTENSION_MODULES,
    reject_behavior_acs_for_extensions,
)
from bob3.spec_quality.spec_extractor import ACFilterResult

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_normal_module.py"


class TestRejectBehaviorAcsForExtensions:
    """Tests for reject_behavior_acs_for_extensions."""

    def test_behavior_ac_rejected_for_verifier_extension(self):
        """Behavior ACs are rejected when primary_diff_target is a verifier module."""
        acs = ["behavior: output MUST contain X"]
        result = reject_behavior_acs_for_extensions(acs, _VERIFIER_TARGET)
        assert result.is_verifier_extension is True
        assert len(result.demoted) == 1
        assert result.demoted[0].original == "behavior: output MUST contain X"
        assert "[SKIP" in result.filtered_acs[0]

    def test_structural_ac_passes_for_verifier_extension(self):
        """Structural ACs pass through for verifier-extension features."""
        acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
        result = reject_behavior_acs_for_extensions(acs, _VERIFIER_TARGET)
        assert result.filtered_acs == acs
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_integration_ac_passes_for_verifier_extension(self):
        """Integration pytest ACs pass through for verifier-extension features."""
        acs = ["integration: pytest tests/test_foo.py::test_bar passes"]
        result = reject_behavior_acs_for_extensions(acs, _VERIFIER_TARGET)
        assert result.filtered_acs == acs
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_normal_feature_unchanged(self):
        """Behavior ACs are NOT rejected for non-verifier-extension features."""
        acs = ["behavior: the API returns 200 status"]
        result = reject_behavior_acs_for_extensions(acs, _NORMAL_TARGET)
        assert result.is_verifier_extension is False
        assert result.filtered_acs == acs
        assert result.demoted == []

    def test_multiple_acs_partial_demotion(self):
        """Mixed ACs: only behavior ACs get demoted; others pass through."""
        acs = [
            "structural: file contains pattern X",
            "behavior: behavior AC that should be rejected",
            "integration: pytest tests/test_x.py",
            "behavior: another rejected behavior AC",
        ]
        result = reject_behavior_acs_for_extensions(acs, _VERIFIER_TARGET)
        assert len(result.demoted) == 2
        assert result.filtered_acs[0] == acs[0]  # structural passes
        assert "[SKIP" in result.filtered_acs[1]  # behavior demoted
        assert result.filtered_acs[2] == acs[2]  # integration passes
        assert "[SKIP" in result.filtered_acs[3]  # behavior demoted

    def test_feature_id_accepted(self):
        """feature_id kwarg is accepted without error."""
        result = reject_behavior_acs_for_extensions(
            ["behavior: test"], _VERIFIER_TARGET, feature_id="feat-123"
        )
        assert result.is_verifier_extension is True
        assert len(result.demoted) == 1

    def test_returns_acfilterresult(self):
        """Return type is ACFilterResult."""
        result = reject_behavior_acs_for_extensions([], _VERIFIER_TARGET)
        assert isinstance(result, ACFilterResult)

    def test_warning_emitted_on_behavior_ac_demotion(self, caplog):
        """A WARNING is logged when a behavior AC is demoted."""
        import logging
        with caplog.at_level(logging.WARNING, logger="verifier.spec_extractor"):
            reject_behavior_acs_for_extensions(
                ["behavior: should warn"], _VERIFIER_TARGET, feature_id="warn-test"
            )
        assert any(
            "behavior AC" in record.message or "behavior" in record.message.lower()
            for record in caplog.records
        )

    def test_all_verifier_extension_modules_trigger_rule(self):
        """Every module in VERIFIER_EXTENSION_MODULES triggers the AC discipline rule."""
        acs = ["behavior: some behavior"]
        for module_path in VERIFIER_EXTENSION_MODULES:
            result = reject_behavior_acs_for_extensions(acs, module_path)
            assert result.is_verifier_extension is True, (
                f"Expected verifier-extension=True for {module_path!r}"
            )
            assert len(result.demoted) == 1, (
                f"Expected demotion for {module_path!r}"
            )

    def test_demoted_record_has_skip_note(self):
        """Demoted AC record contains a skip_note with structural/integration suggestion."""
        acs = ["behavior: some output behavior"]
        result = reject_behavior_acs_for_extensions(acs, _VERIFIER_TARGET)
        assert len(result.demoted) == 1
        skip_note = result.demoted[0].skip_note
        assert "structural" in skip_note.lower() or "integration" in skip_note.lower()

    def test_verifier_extension_modules_non_empty_tuple(self):
        """VERIFIER_EXTENSION_MODULES is a non-empty tuple of strings."""
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert len(VERIFIER_EXTENSION_MODULES) > 0
        for path in VERIFIER_EXTENSION_MODULES:
            assert isinstance(path, str)


class TestIntegrationWithSpecExtractor:
    """Tests that verifier.spec_extractor integrates with bob3.spec_quality.spec_extractor."""

    def test_same_verifier_extension_modules(self):
        """verifier.spec_extractor uses same VERIFIER_EXTENSION_MODULES as bob3."""
        from bob3.spec_quality.spec_extractor import (
            VERIFIER_EXTENSION_MODULES as BOB3_MODULES,
        )
        from verifier.spec_extractor import (
            VERIFIER_EXTENSION_MODULES as VERIFIER_MODULES,
        )
        assert VERIFIER_MODULES == BOB3_MODULES

    def test_consistent_demotion_behavior(self):
        """verifier.spec_extractor and bob3.spec_extractor agree on demotion."""
        from bob3.spec_quality.spec_extractor import (
            filter_behavior_acs_for_verifier_extension,
        )
        acs = ["behavior: test behavior", "structural: test structural"]
        result_verifier = reject_behavior_acs_for_extensions(acs, _VERIFIER_TARGET)
        result_bob3 = filter_behavior_acs_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert len(result_verifier.demoted) == len(result_bob3.demoted)
        assert result_verifier.is_verifier_extension == result_bob3.is_verifier_extension
