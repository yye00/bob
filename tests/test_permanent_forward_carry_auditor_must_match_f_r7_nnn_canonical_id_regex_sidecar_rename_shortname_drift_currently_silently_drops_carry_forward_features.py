"""Tests for the canonical-ID-regex matching auditor.

Feature: Permanent-forward-carry auditor MUST match by F-R7-NNN canonical ID
regex — sidecar rename or shortname drift currently silently drops carry-forward
features.

Root problem: exact 'id' field string matching misses required features when the
sidecar is renamed (e.g. bob26-unlimited-spawn-retry → bob27-unlimited-spawn-retry)
or when only the shortname appears in the 'id' field while the canonical token
is in the title/description. This module audits by regex scan across all text
fields so renames and shortname drift are detected correctly.
"""

from __future__ import annotations

import pytest

import bob3.permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features as auditor_module
from bob3.permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features import (
    BootstrapAuditError,
    _CANONICAL_REQUIRED_IDS,
    _COMPILED_CANONICAL_PATTERN,
    extract_canonical_ids,
    fail_loud_on_missing,
    permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features as audit_fn,
    required_feature_ids,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec_with_ids(*ids: str) -> dict:
    """Build a spec where every entry has an exact canonical ID in the id field."""
    return {
        "features": [
            {"id": fid, "title": f"Feature {fid}", "description": "test feature"}
            for fid in ids
        ]
    }


def _spec_with_renamed_sidecar(canonical_id: str, sidecar_name: str) -> dict:
    """Build a spec entry that has a sidecar alias as 'id' but the canonical ID in title."""
    return {
        "features": [
            {
                "id": sidecar_name,
                "title": f"{canonical_id} Permanent carry feature",
                "description": f"Implements {canonical_id} capability",
            }
        ]
    }


def _spec_with_shortname_only(shortname: str) -> dict:
    """Build a spec entry that has only a shortname — no canonical ID token anywhere."""
    return {
        "features": [
            {
                "id": shortname,
                "title": "Unnamed carry feature",
                "description": "carry feature without canonical ID token",
            }
        ]
    }


# ---------------------------------------------------------------------------
# AC function exists and is callable
# ---------------------------------------------------------------------------

class TestFunctionExists:
    """AC: Function defined in the module."""

    def test_function_defined_in_module(self):
        assert hasattr(auditor_module, "permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features")

    def test_function_is_callable(self):
        assert callable(audit_fn)

    def test_module_all_includes_function(self):
        assert "permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features" in auditor_module.__all__


# ---------------------------------------------------------------------------
# Primary AC test (required by pytest: AC)
# ---------------------------------------------------------------------------

def test_permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features():
    """Single consolidated test satisfying the pytest: AC line.

    Verifies:
    1. An exact-ID spec passes without raising.
    2. A sidecar-renamed spec where canonical ID appears in the title also passes.
    3. A spec that has only a shortname (no canonical token anywhere) fails with
       BootstrapAuditError.
    4. The error message contains 'permanent_forward_carry_missing'.
    5. Return value is an empty frozenset on success.
    """
    # 1. Exact canonical IDs in id field → should pass
    spec_exact = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
    result = audit_fn(spec_exact)
    assert result == frozenset(), f"Expected no missing, got {result}"

    # 2. Sidecar-renamed id field, canonical token in title → should pass
    spec_renamed = {
        "features": [
            {
                "id": "bob27-unlimited-spawn-retry",
                "title": "F-R7-478 Unlimited spawn retry (bob27 sidecar)",
                "description": "Sidecar rename of the bob26 implementation",
            },
            {"id": "F-R7-479", "title": "RCA NH auto-reset", "description": ""},
            {"id": "F-R7-553", "title": "Slopsquatting whitelist", "description": ""},
        ]
    }
    result_renamed = audit_fn(spec_renamed)
    assert result_renamed == frozenset(), f"Renamed sidecar should pass regex scan, got {result_renamed}"

    # 3. Shortname-only, no canonical token → should raise
    spec_shortname = {
        "features": [
            {"id": "unlimited-spawn-retry", "title": "carry feature", "description": "carry"},
            {"id": "rca-nh-auto-reset", "title": "carry feature", "description": "carry"},
            {"id": "slopsquatting-wall", "title": "carry feature", "description": "carry"},
        ]
    }
    with pytest.raises(BootstrapAuditError) as exc_info:
        audit_fn(spec_shortname)

    # 4. Error message contains the structured event token
    assert "permanent_forward_carry_missing" in str(exc_info.value)

    # 5. The error lists at least one of the required IDs
    error_msg = str(exc_info.value)
    assert any(fid in error_msg for fid in ("F-R7-478", "F-R7-479", "F-R7-553"))


# ---------------------------------------------------------------------------
# Sidecar rename scenarios
# ---------------------------------------------------------------------------

class TestSidecarRenameDetection:
    """Audit passes when canonical ID appears in title/description despite renamed id."""

    def test_canonical_id_in_title_satisfies_audit(self):
        """F-R7-478 in title satisfies audit even when id field is a sidecar alias."""
        spec = {
            "features": [
                {
                    "id": "bob27-unlimited-spawn-retry",
                    "title": "F-R7-478 Unlimited spawn retry",
                    "description": "",
                },
                {"id": "F-R7-479", "title": "RCA NH auto-reset", "description": ""},
                {"id": "F-R7-553", "title": "Slopsquatting whitelist", "description": ""},
            ]
        }
        result = audit_fn(spec)
        assert result == frozenset()

    def test_canonical_id_in_description_satisfies_audit(self):
        """F-R7-479 in description satisfies audit when id is a shortname."""
        spec = {
            "features": [
                {"id": "F-R7-478", "title": "Unlimited spawn retry", "description": ""},
                {
                    "id": "nh-auto-reset",
                    "title": "Auto-reset feature",
                    "description": "Implements F-R7-479 reset logic",
                },
                {"id": "F-R7-553", "title": "Slopsquatting whitelist", "description": ""},
            ]
        }
        result = audit_fn(spec)
        assert result == frozenset()

    def test_bob26_to_bob27_shuffle_still_detected(self):
        """bob26 → bob27 sidecar shuffle does not drop the required feature."""
        spec = {
            "features": [
                {
                    "id": "bob27-feature",
                    "title": "F-R7-478 carry (was bob26-unlimited-spawn-retry)",
                    "description": "Renamed in bob27 shuffle",
                },
                {"id": "F-R7-479", "title": "RCA NH auto-reset", "description": ""},
                {"id": "F-R7-553", "title": "Slopsquatting whitelist", "description": ""},
            ]
        }
        result = audit_fn(spec)
        assert result == frozenset()

    def test_multiple_renamed_sidecars_all_detected(self):
        """All three required IDs found via title tokens despite all id fields being aliases."""
        spec = {
            "features": [
                {
                    "id": "alias-a",
                    "title": "F-R7-478 Feature",
                    "description": "unlimited spawn",
                },
                {
                    "id": "alias-b",
                    "title": "F-R7-479 Feature",
                    "description": "nh auto-reset",
                },
                {
                    "id": "alias-c",
                    "title": "F-R7-553 Feature",
                    "description": "slopsquatting wall",
                },
            ]
        }
        result = audit_fn(spec)
        assert result == frozenset()


# ---------------------------------------------------------------------------
# Shortname-only drift scenarios (should fail)
# ---------------------------------------------------------------------------

class TestShortnameDriftFailure:
    """Audit fails when required IDs appear nowhere as F-R7-NNN tokens."""

    def test_shortname_only_raises_bootstrap_audit_error(self):
        """A spec with only shortnames and no F-R7-NNN tokens fails."""
        spec = {
            "features": [
                {"id": "unlimited-spawn-retry", "title": "Spawn retry", "description": ""},
                {"id": "nh-auto-reset", "title": "NH reset", "description": ""},
                {"id": "slopsquatting-wall", "title": "Slopsquatting", "description": ""},
            ]
        }
        with pytest.raises(BootstrapAuditError):
            audit_fn(spec)

    def test_error_lists_all_missing_ids(self):
        """Error message lists all missing canonical IDs."""
        spec = {"features": []}
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_fn(spec)
        error_msg = str(exc_info.value)
        assert "F-R7-478" in error_msg
        assert "F-R7-479" in error_msg
        assert "F-R7-553" in error_msg

    def test_error_missing_attribute_contains_missing_ids(self):
        """BootstrapAuditError.missing contains the absent IDs."""
        spec = {"features": [{"id": "F-R7-478", "title": "F-R7-478 feature", "description": ""}]}
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_fn(spec)
        assert "F-R7-479" in exc_info.value.missing
        assert "F-R7-553" in exc_info.value.missing


# ---------------------------------------------------------------------------
# Return value contract
# ---------------------------------------------------------------------------

class TestReturnValue:
    """audit_fn returns frozenset of missing IDs (empty on success)."""

    def test_returns_empty_frozenset_on_full_spec(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        result = audit_fn(spec)
        assert isinstance(result, frozenset)
        assert result == frozenset()

    def test_raises_not_returns_on_missing(self):
        """Function raises rather than returning a non-empty set."""
        spec = _spec_with_ids("F-R7-478")
        with pytest.raises(BootstrapAuditError):
            audit_fn(spec)


# ---------------------------------------------------------------------------
# Custom required set override
# ---------------------------------------------------------------------------

class TestCustomRequiredSet:
    """required= kwarg lets callers audit against a custom ID set."""

    def test_custom_required_set_passes_when_present(self):
        spec = {
            "features": [
                {"id": "F-R7-999", "title": "Custom feature F-R7-999", "description": ""},
            ]
        }
        result = audit_fn(spec, required=frozenset({"F-R7-999"}))
        assert result == frozenset()

    def test_custom_required_set_fails_when_absent(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        with pytest.raises(BootstrapAuditError) as exc_info:
            audit_fn(spec, required=frozenset({"F-R7-999"}))
        assert "F-R7-999" in str(exc_info.value)

    def test_none_required_uses_default_set(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        result = audit_fn(spec, required=None)
        assert result == frozenset()


# ---------------------------------------------------------------------------
# Spec format variants
# ---------------------------------------------------------------------------

class TestSpecFormatVariants:
    """Auditor works with both list-of-dicts and dict-of-dicts formats."""

    def test_list_format_with_exact_ids_passes(self):
        spec = _spec_with_ids("F-R7-478", "F-R7-479", "F-R7-553")
        assert audit_fn(spec) == frozenset()

    def test_dict_of_dicts_format_passes(self):
        spec = {
            "features": {
                "F-R7-478": {"title": "Unlimited spawn retry"},
                "F-R7-479": {"title": "RCA NH auto-reset"},
                "F-R7-553": {"title": "Slopsquatting whitelist"},
            }
        }
        assert audit_fn(spec) == frozenset()

    def test_empty_spec_raises(self):
        with pytest.raises(BootstrapAuditError):
            audit_fn({})

    def test_no_features_key_raises(self):
        with pytest.raises(BootstrapAuditError):
            audit_fn({"other_key": "value"})

    def test_empty_features_list_raises(self):
        with pytest.raises(BootstrapAuditError):
            audit_fn({"features": []})


# ---------------------------------------------------------------------------
# Re-exported symbols
# ---------------------------------------------------------------------------

class TestReExports:
    """Module re-exports the expected underlying symbols."""

    def test_bootstrap_audit_error_available(self):
        assert BootstrapAuditError is not None

    def test_canonical_required_ids_available(self):
        assert isinstance(_CANONICAL_REQUIRED_IDS, frozenset)

    def test_compiled_canonical_pattern_available(self):
        import re
        assert isinstance(_COMPILED_CANONICAL_PATTERN, re.Pattern)

    def test_extract_canonical_ids_available(self):
        assert callable(extract_canonical_ids)

    def test_required_feature_ids_available(self):
        assert callable(required_feature_ids)

    def test_fail_loud_on_missing_available(self):
        assert callable(fail_loud_on_missing)
