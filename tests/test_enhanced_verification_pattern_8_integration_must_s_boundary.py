"""Boundary-case tests for Pattern 8 integration AC handler.

Feature bde55fc0-2023-46ce-98f0-4de4125824df:
Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens in body AND
demote prose-policy integration ACs to warning.

This file tests boundary/edge inputs: empty, whitespace-only, and minimum inputs
must return a well-defined result rather than raising unexpectedly.
"""

from __future__ import annotations

import pathlib

import pytest


class TestBoundaryInputs:
    """Empty, zero, or minimum inputs must return a well-defined result."""

    def test_empty_criterion_returns_false(self, tmp_path):
        """Empty string criterion returns (False, reason) without crashing."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("", tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)
        assert not passed

    def test_whitespace_only_criterion_returns_false(self, tmp_path):
        """Whitespace-only criterion returns (False, reason) without crashing."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("   \t\n  ", tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)
        assert not passed

    def test_integration_marker_only_no_body(self, tmp_path):
        """'integration:' with no body returns a well-defined result."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("integration:", tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)

    def test_integration_marker_with_only_spaces(self, tmp_path):
        """'integration:   ' with only spaces after returns a well-defined result."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("integration:   ", tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)

    def test_minimum_valid_criterion_with_one_dotted_token(self, tmp_path):
        """Minimum valid integration criterion with one dotted token returns a result."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        # A simple non-existent module — should hard-fail cleanly
        passed, reason = resolve_integration_ac("integration: a.b", tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)
        # tmp_path has no src/ — so should not resolve
        assert not passed

    def test_no_integration_marker_returns_false(self, tmp_path):
        """Criterion without 'integration:' returns (False, ...) not crashes."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("behavior: something happens", tmp_path)
        assert not passed
        assert isinstance(reason, str)

    def test_extract_integration_targets_empty_string(self):
        """extract_integration_targets with empty string returns []."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("")
        assert result == []

    def test_extract_integration_targets_whitespace_only(self):
        """extract_integration_targets with whitespace-only string returns []."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("   ")
        assert result == []

    def test_extract_integration_targets_no_marker(self):
        """extract_integration_targets without 'integration:' returns []."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("file exists: something")
        assert result == []

    def test_extract_integration_targets_marker_only(self):
        """extract_integration_targets with just 'integration:' returns []."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("integration:")
        assert result == []

    def test_log_integration_ac_prose_demoted_empty_candidates(self, caplog):
        """log_integration_ac_prose_demoted with empty candidates list does not crash."""
        import logging
        from bob3.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        with caplog.at_level(logging.INFO, logger="bob3.verification.integration_demotion"):
            log_integration_ac_prose_demoted("integration: foo", None, [])

        # Just verify it ran without crashing and emitted something
        assert any(
            "INTEGRATION_AC_PROSE_DEMOTED" in record.message
            for record in caplog.records
        )

    def test_resolve_with_none_feature_id_in_prose_demotion(self, tmp_path):
        """Prose demotion works when feature_id is None (no crash)."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: all writes must route through the atomic writer"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)
        # Prose body — must demote to warning (True)
        assert passed, f"Prose body must demote to warning; got passed={passed!r}"
