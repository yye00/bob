"""Tests for the permanent-forward-carry bootstrap auditor.

Covers:
- Empty-set return when all required features are present
- Missing-set return + BootstrapAuditError when F-R7-478 is absent
- Env-var addition extends the required set without replacing the base
"""

from __future__ import annotations

import os
import pytest

from bob3.permanent_forward_carry_auditor import (
    BootstrapAuditError,
    _CANONICAL_REQUIRED_IDS,
    audit_bootstrap_spec,
    audit_merged_spec,
    fail_loud_on_missing,
    required_feature_ids,
)


def _spec_with_ids(*ids: str) -> dict:
    """Build a minimal spec dict that declares the given feature IDs."""
    return {
        "features": [
            {"id": fid, "title": f"Feature {fid}", "description": "test"}
            for fid in ids
        ]
    }


class TestRequiredFeatureIds:
    """Tests for required_feature_ids()."""

    def test_returns_frozenset(self):
        result = required_feature_ids()
        assert isinstance(result, frozenset)

    def test_contains_canonical_base(self):
        result = required_feature_ids()
        assert "F-R7-478" in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result

    def test_base_set_is_minimum(self):
        result = required_feature_ids()
        assert _CANONICAL_REQUIRED_IDS.issubset(result)

    def test_env_var_adds_not_replaces(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", "F-CUSTOM-001,F-CUSTOM-002")
        result = required_feature_ids()
        # Base set still present
        assert "F-R7-478" in result
        assert "F-R7-479" in result
        assert "F-R7-553" in result
        # Extra IDs added
        assert "F-CUSTOM-001" in result
        assert "F-CUSTOM-002" in result

    def test_env_var_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", " F-EXTRA-999 , F-EXTRA-888 ")
        result = required_feature_ids()
        assert "F-EXTRA-999" in result
        assert "F-EXTRA-888" in result

    def test_empty_env_var_uses_base_only(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", "")
        result = required_feature_ids()
        assert result == _CANONICAL_REQUIRED_IDS


class TestAuditMergedSpec:
    """Tests for audit_merged_spec()."""

    def test_empty_set_when_all_required_features_present(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert missing == frozenset(), f"Expected no missing features, got: {missing}"

    def test_missing_set_when_f_r7_478_absent(self):
        spec = _spec_with_ids("F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert "F-R7-478" in missing, f"Expected F-R7-478 in missing, got: {missing}"

    def test_missing_set_when_f_r7_479_absent(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert "F-R7-479" in missing

    def test_missing_set_when_f_r7_553_absent(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479")
        missing = audit_merged_spec(spec)
        assert "F-R7-553" in missing

    def test_multiple_missing_ids_reported(self):
        spec = _spec_with_ids("F-OTHER-001")
        missing = audit_merged_spec(spec)
        assert "F-R7-478" in missing
        assert "F-R7-479" in missing
        assert "F-R7-553" in missing

    def test_returns_frozenset(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        result = audit_merged_spec(spec)
        assert isinstance(result, frozenset)

    def test_dict_of_dicts_features_format(self):
        spec = {
            "features": {
                "F-R7-478": {"title": "Unlimited spawn retry", "description": "..."},
                "F-R7-479": {"title": "RCA NH auto-reset", "description": "..."},
                "F-R7-553": {"title": "Slopsquatting whitelist", "description": "..."},
            }
        }
        missing = audit_merged_spec(spec)
        assert missing == frozenset()

    def test_extra_features_beyond_required_are_ignored(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553", "F-OTHER-999")
        missing = audit_merged_spec(spec)
        assert missing == frozenset()

    def test_empty_spec_reports_all_missing(self):
        spec = {}
        missing = audit_merged_spec(spec)
        assert "F-R7-478" in missing
        assert "F-R7-479" in missing
        assert "F-R7-553" in missing

    def test_spec_with_no_features_key_reports_all_missing(self):
        spec = {"name": "test-project", "version": "1.0"}
        missing = audit_merged_spec(spec)
        assert len(missing) == 3

    def test_env_var_extended_set_is_checked(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", "F-CUSTOM-777")
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert "F-CUSTOM-777" in missing


class TestFailLoudOnMissing:
    """Tests for fail_loud_on_missing()."""

    def test_raises_bootstrap_audit_error_when_missing_non_empty(self):
        missing = frozenset({"F-R7-478"})
        with pytest.raises(BootstrapAuditError):
            fail_loud_on_missing(missing)

    def test_error_message_lists_missing_ids(self):
        missing = frozenset({"F-R7-478", "F-R7-479"})
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(missing)
        msg = str(exc_info.value)
        assert "F-R7-478" in msg
        assert "F-R7-479" in msg

    def test_error_message_points_to_staged_specs(self):
        missing = frozenset({"F-R7-478"})
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(missing)
        assert "bob4/research/staged_specs/" in str(exc_info.value)

    def test_error_contains_permanent_forward_carry_missing_event(self):
        missing = frozenset({"F-R7-553"})
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(missing)
        assert "permanent_forward_carry_missing" in str(exc_info.value)

    def test_no_error_when_missing_is_empty(self):
        fail_loud_on_missing(frozenset())

    def test_bootstrap_audit_error_stores_missing_set(self):
        missing = frozenset({"F-R7-478", "F-R7-553"})
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(missing)
        assert exc_info.value.missing == missing

    def test_raises_for_env_extended_missing(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", "F-CUSTOM-001")
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert "F-CUSTOM-001" in missing
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(missing)
        assert "F-CUSTOM-001" in str(exc_info.value)


class TestIntegrationAuditAndFail:
    """Integration: audit_merged_spec + fail_loud_on_missing together."""

    def test_full_spec_passes_silently(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        fail_loud_on_missing(missing)  # Should not raise

    def test_spec_missing_f_r7_478_raises(self):
        spec = _spec_with_ids("F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert missing
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(missing)
        assert "F-R7-478" in str(exc_info.value)

    def test_existing_f_r7_478_and_f_r7_479_satisfy_audit(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        missing = audit_merged_spec(spec)
        assert "F-R7-478" not in missing
        assert "F-R7-479" not in missing

    def test_env_var_addition_extends_required_set_no_replacement(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", "F-NEW-100")
        ids = required_feature_ids()
        # Base must still be present
        assert "F-R7-478" in ids
        assert "F-R7-479" in ids
        assert "F-R7-553" in ids
        # Extension present
        assert "F-NEW-100" in ids
        # Verify base set size check: extended is strictly larger
        assert len(ids) > len(_CANONICAL_REQUIRED_IDS)


class TestAuditBootstrapSpec:
    """Tests for audit_bootstrap_spec() — single-call auditor entrypoint."""

    def test_returns_none_when_all_required_present(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        result = audit_bootstrap_spec(spec)
        assert result is None

    def test_raises_bootstrap_audit_error_when_f_r7_478_missing(self):
        spec = _spec_with_ids("F-R7-479", "F-R7-553")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "F-R7-478" in str(exc_info.value)

    def test_raises_bootstrap_audit_error_when_f_r7_479_missing(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-553")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "F-R7-479" in str(exc_info.value)

    def test_raises_bootstrap_audit_error_when_f_r7_553_missing(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "F-R7-553" in str(exc_info.value)

    def test_raises_with_permanent_forward_carry_missing_event(self):
        spec = _spec_with_ids("F-R7-478")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "permanent_forward_carry_missing" in str(exc_info.value)

    def test_raises_with_staged_specs_pointer(self):
        spec = {}
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "bob4/research/staged_specs/" in str(exc_info.value)

    def test_error_stores_missing_set(self):
        spec = _spec_with_ids("F-R7-553")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "F-R7-478" in exc_info.value.missing
        assert "F-R7-479" in exc_info.value.missing

    def test_dict_of_dicts_spec_passes(self):
        spec = {
            "features": {
                "F-R7-478": {"title": "Unlimited spawn retry"},
                "F-R7-479": {"title": "RCA NH auto-reset"},
                "F-R7-553": {"title": "Slopsquatting whitelist"},
            }
        }
        audit_bootstrap_spec(spec)  # Should not raise

    def test_env_var_extended_id_causes_failure(self, monkeypatch):
        monkeypatch.setenv("BOB3_PERMANENT_CARRY_IDS", "F-CUSTOM-444")
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_bootstrap_spec(spec)
        assert "F-CUSTOM-444" in str(exc_info.value)
