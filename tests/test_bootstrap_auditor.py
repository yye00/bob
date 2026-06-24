"""Tests for bob.bootstrap_auditor — permanent-forward-carry bootstrap check.

Verifies:
- audit_permanent_forward_carry exists and is callable
- PermanentForwardCarryMissing is a defined class (not an alias)
- Passes silently when F-R7-478, F-R7-479, and F-R7-553 are all present
- Raises PermanentForwardCarryMissing when any required ID is absent
- Error message contains permanent_forward_carry_missing event string
- Error message points to bob4/research/staged_specs/
- Exception .missing attribute holds the frozenset of absent IDs
"""

from __future__ import annotations

import pytest

from bob.bootstrap_auditor import (
    BootstrapAuditError,
    PermanentForwardCarryMissing,
    audit_permanent_forward_carry,
    required_feature_ids,
)


def _spec(*ids: str) -> dict:
    return {
        "features": [
            {"id": fid, "title": f"Feature {fid}", "description": "test"}
            for fid in ids
        ]
    }


class TestAuditPermanentForwardCarryExists:
    """Module-level symbol checks."""

    def test_audit_permanent_forward_carry_is_callable(self):
        assert callable(audit_permanent_forward_carry)

    def test_permanent_forward_carry_missing_is_class(self):
        assert isinstance(PermanentForwardCarryMissing, type)

    def test_permanent_forward_carry_missing_is_exception_subclass(self):
        assert issubclass(PermanentForwardCarryMissing, Exception)

    def test_bootstrap_audit_error_is_class(self):
        assert isinstance(BootstrapAuditError, type)

    def test_permanent_forward_carry_missing_is_subclass_of_bootstrap_audit_error(self):
        assert issubclass(PermanentForwardCarryMissing, BootstrapAuditError)


class TestAuditPermanentForwardCarryPass:
    """Passes silently when all required features are present."""

    def test_all_three_required_ids_present_no_raise(self):
        spec = _spec("F-R7-478", "F-R7-479", "F-R7-553")
        result = audit_permanent_forward_carry(spec)
        assert result is None

    def test_extra_features_beyond_required_no_raise(self):
        spec = _spec("F-R7-478", "F-R7-479", "F-R7-553", "F-OTHER-001")
        audit_permanent_forward_carry(spec)

    def test_dict_of_dicts_features_format_passes(self):
        spec = {
            "features": {
                "F-R7-478": {"title": "Unlimited spawn retry"},
                "F-R7-479": {"title": "RCA NH auto-reset"},
                "F-R7-553": {"title": "Slopsquatting whitelist"},
            }
        }
        audit_permanent_forward_carry(spec)


class TestAuditPermanentForwardCarryRaises:
    """Raises PermanentForwardCarryMissing when any required ID is absent."""

    def test_raises_when_f_r7_478_absent(self):
        spec = _spec("F-R7-479", "F-R7-553")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert "F-R7-478" in str(exc_info.value)

    def test_raises_when_f_r7_479_absent(self):
        spec = _spec("F-R7-478", "F-R7-553")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert "F-R7-479" in str(exc_info.value)

    def test_raises_when_f_r7_553_absent(self):
        spec = _spec("F-R7-478", "F-R7-479")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert "F-R7-553" in str(exc_info.value)

    def test_raises_when_all_three_absent(self):
        spec = {}
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        missing = exc_info.value.missing
        assert "F-R7-478" in missing
        assert "F-R7-479" in missing
        assert "F-R7-553" in missing

    def test_error_contains_permanent_forward_carry_missing_event(self):
        spec = _spec("F-R7-478")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert "permanent_forward_carry_missing" in str(exc_info.value)

    def test_error_points_to_staged_specs(self):
        spec = _spec("F-R7-479", "F-R7-553")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert "bob4/research/staged_specs/" in str(exc_info.value)

    def test_exception_missing_attribute_holds_absent_ids(self):
        spec = _spec("F-R7-553")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert isinstance(exc_info.value.missing, frozenset)
        assert "F-R7-478" in exc_info.value.missing
        assert "F-R7-479" in exc_info.value.missing

    def test_exception_is_also_catchable_as_bootstrap_audit_error(self):
        spec = _spec("F-R7-479")
        with pytest.raises(BootstrapAuditError):
            audit_permanent_forward_carry(spec)

    def test_single_feature_present_two_absent_lists_both(self):
        spec = _spec("F-R7-553")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        err = str(exc_info.value)
        assert "F-R7-478" in err
        assert "F-R7-479" in err


class TestAuditPermanentForwardCarryEnvExtension:
    """Env-var BOB_PERMANENT_CARRY_IDS extends required set without replacing base."""

    def test_env_var_extended_id_causes_failure(self, monkeypatch):
        monkeypatch.setenv("BOB_PERMANENT_CARRY_IDS", "F-CUSTOM-444")
        spec = _spec("F-R7-478", "F-R7-479", "F-R7-553")
        with pytest.raises(PermanentForwardCarryMissing) as exc_info:
            audit_permanent_forward_carry(spec)
        assert "F-CUSTOM-444" in str(exc_info.value)

    def test_env_var_does_not_replace_base_set(self, monkeypatch):
        monkeypatch.setenv("BOB_PERMANENT_CARRY_IDS", "F-EXTRA-999")
        ids = required_feature_ids()
        assert "F-R7-478" in ids
        assert "F-R7-479" in ids
        assert "F-R7-553" in ids
        assert "F-EXTRA-999" in ids
