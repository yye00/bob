"""Tests for hippy.permanent_forward_carry_auditor.

Verifies canonical F-R7-NNN regex matching survives sidecar rename and
shortname drift — the F-R7-554 silent-drop fix.
"""

from __future__ import annotations

import pytest

from hippy.permanent_forward_carry_auditor import (
    ForwardCarryAuditError,
    audit_forward_carry,
    match_canonical_feature_id,
    required_feature_ids,
)


def _spec(*entries: dict) -> dict:
    return {"features": list(entries)}


class TestMatchCanonicalFeatureId:
    def test_exact_id_match(self):
        assert match_canonical_feature_id({"id": "F-R7-478"}, "F-R7-478") is True

    def test_token_in_title_when_id_is_renamed_sidecar(self):
        # Sidecar renamed: id no longer equals the canonical string, but the
        # token survives in the title — must still be detected.
        entry = {"id": "bob27-shuffle", "title": "carry (F-R7-478)"}
        assert match_canonical_feature_id(entry, "F-R7-478") is True

    def test_token_in_description(self):
        entry = {"id": "x", "title": "y", "description": "keeps F-R7-553 alive"}
        assert match_canonical_feature_id(entry, "F-R7-553") is True

    def test_word_boundary_prevents_prefix_match(self):
        entry = {"id": "F-R7-478"}
        assert match_canonical_feature_id(entry, "F-R7-47") is False

    def test_absent_token_returns_false(self):
        assert match_canonical_feature_id({"id": "F-R7-999"}, "F-R7-478") is False

    def test_empty_dict_returns_false(self):
        assert match_canonical_feature_id({}, "F-R7-478") is False

    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_canonical_feature_id(["F-R7-478"], "F-R7-478")

    def test_empty_canonical_id_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            match_canonical_feature_id({"id": "F-R7-478"}, "")

    def test_letters_only_id_raises(self):
        with pytest.raises(ValueError):
            match_canonical_feature_id({"id": "F-R7-478"}, "FEATURE")


class TestAuditForwardCarry:
    def test_all_present_returns_empty(self):
        spec = _spec(
            {"id": "F-R7-478"}, {"id": "F-R7-479"}, {"id": "F-R7-553"}
        )
        assert audit_forward_carry(spec) == frozenset()

    def test_renamed_sidecar_still_detected(self):
        # id fields renamed away from canonical strings; tokens live in title.
        spec = _spec(
            {"id": "a", "title": "F-R7-478"},
            {"id": "b", "title": "F-R7-479"},
            {"id": "c", "title": "F-R7-553"},
        )
        assert audit_forward_carry(spec) == frozenset()

    def test_missing_reported(self):
        spec = _spec({"id": "F-R7-479"}, {"id": "F-R7-553"})
        assert "F-R7-478" in audit_forward_carry(spec)

    def test_dict_of_dicts_format(self):
        spec = {
            "features": {
                "F-R7-478": {"title": "F-R7-478"},
                "F-R7-479": {"title": "F-R7-479"},
                "F-R7-553": {"title": "F-R7-553"},
            }
        }
        assert audit_forward_carry(spec) == frozenset()

    def test_empty_spec_reports_all_missing(self):
        missing = audit_forward_carry({})
        assert missing == required_feature_ids()

    def test_raise_on_missing(self):
        with pytest.raises(ForwardCarryAuditError) as exc:
            audit_forward_carry({}, raise_on_missing=True)
        assert "permanent_forward_carry_missing" in str(exc.value)
        assert exc.value.missing == required_feature_ids()

    def test_non_dict_spec_raises(self):
        with pytest.raises(ValueError, match="spec must be a dict"):
            audit_forward_carry(["F-R7-478"])

    def test_env_var_extends_required(self, monkeypatch):
        monkeypatch.setenv("BOB_PERMANENT_CARRY_IDS", "F-CUSTOM-001")
        spec = _spec({"id": "F-R7-478"}, {"id": "F-R7-479"}, {"id": "F-R7-553"})
        assert "F-CUSTOM-001" in audit_forward_carry(spec)
