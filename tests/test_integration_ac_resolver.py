"""Tests for bob.verification.integration_ac_resolver.

Feature bde55fc0-2023-46ce-98f0-4de4125824df:
Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens in body AND
demote prose-policy integration ACs to warning.

This module tests the canonical integration_ac_resolver module at
src/bob/verification/integration_ac_resolver.py.
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest


class TestExtractIntegrationTargets:
    """Tests for extract_integration_targets function."""

    def test_extracts_dotted_tokens(self):
        """Returns dotted tokens from body after 'integration:'."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        criterion = "integration: all writes in bob.reviews route through atomic_write_yaml"
        targets = extract_integration_targets(criterion)
        assert "bob.reviews" in targets

    def test_does_not_include_first_word_if_undotted(self):
        """The first word 'all' is not returned since it has no dots."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        criterion = "integration: all spec_findings.yaml writes in bob.reviews route through atomic_write_yaml"
        targets = extract_integration_targets(criterion)
        assert "all" not in targets

    def test_returns_multiple_dotted_tokens(self):
        """Returns all dotted tokens when multiple are present."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        criterion = "integration: bob.x.y and bob.a.b are both imported"
        targets = extract_integration_targets(criterion)
        assert "bob.x.y" in targets
        assert "bob.a.b" in targets

    def test_returns_empty_for_no_dotted_tokens(self):
        """Returns empty list when no dotted tokens exist."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        criterion = "integration: ensure all tests pass"
        targets = extract_integration_targets(criterion)
        assert isinstance(targets, list)
        for t in targets:
            assert "." in t, f"Non-dotted token {t!r} should not appear"

    def test_returns_empty_for_no_integration_marker(self):
        """Returns empty list if 'integration:' is absent."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        targets = extract_integration_targets("behavior: something happens")
        assert targets == []

    def test_non_string_returns_empty(self):
        """Non-string input returns empty list rather than raising."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        assert extract_integration_targets(None) == []  # type: ignore[arg-type]
        assert extract_integration_targets(123) == []  # type: ignore[arg-type]

    def test_c09e9e64_regression_form(self):
        """Regression: the exact c09e9e64 criterion form extracts bob.reviews."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        criterion = (
            "integration: all spec_findings.yaml writes in bob.reviews route "
            "through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
        )
        targets = extract_integration_targets(criterion)
        assert "bob.reviews" in targets, (
            f"Expected 'bob.reviews' in targets, got: {targets}"
        )


class TestResolveIntegrationAc:
    """Tests for resolve_integration_ac function."""

    @pytest.fixture
    def real_workspace(self) -> pathlib.Path:
        """Return the actual bob workspace root."""
        return pathlib.Path(__file__).parent.parent

    def test_returns_true_for_wired_module(self, real_workspace):
        """A real wired module returns (True, '')."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: bob.verification module exists"
        passed, reason = resolve_integration_ac(criterion, real_workspace)
        assert passed, (
            f"Expected passed=True for wired module, got passed={passed!r} reason={reason!r}"
        )

    def test_prose_body_demotes_to_warning(self, tmp_path):
        """A prose body with no resolvable modules returns (True, demotion message)."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        criterion = (
            "integration: all writes must route through the atomic writer "
            "and no direct yaml.dump calls remain"
        )
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        assert passed, f"Prose body must demote to warning; got passed={passed!r}"
        assert "demoted" in reason.lower() or reason == "", (
            f"Expected demotion message, got: {reason!r}"
        )

    def test_unwired_single_dotted_returns_false(self, tmp_path):
        """A single dotted target not in any src file returns (False, ...)."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: bob.totally.nonexistent.xyz"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        # Body has no spaces — not prose — should hard-fail
        assert not passed, (
            f"Non-existent module should return False; got passed={passed!r}"
        )

    def test_no_integration_marker_returns_false(self, tmp_path):
        """Criterion without 'integration:' returns (False, ...)."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("behavior: something", tmp_path)
        assert not passed
        assert isinstance(reason, str)

    def test_c09e9e64_regression_form_does_not_hard_fail(self, real_workspace):
        """The c09e9e64 criterion must not hard-fail (prose demotion expected)."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        criterion = (
            "integration: all spec_findings.yaml writes in bob.reviews route "
            "through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
        )
        passed, reason = resolve_integration_ac(criterion, real_workspace)
        assert passed, (
            f"c09e9e64 criterion must not hard-fail; got passed={passed!r} reason={reason!r}"
        )


class TestLogIntegrationAcProseDemoted:
    """Tests for log_integration_ac_prose_demoted function."""

    def test_emits_structured_log_with_event_key(self, caplog):
        """log_integration_ac_prose_demoted emits a JSON log with event='INTEGRATION_AC_PROSE_DEMOTED'."""
        from bob.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        criterion = "integration: all writes route through atomic_write_yaml"
        feature_id = "test-feature-id"
        candidates = ["bob.reviews"]

        with caplog.at_level(logging.INFO, logger="bob.verification.integration_demotion"):
            log_integration_ac_prose_demoted(criterion, feature_id, candidates)

        assert any(
            "INTEGRATION_AC_PROSE_DEMOTED" in record.message
            for record in caplog.records
        ), f"Expected INTEGRATION_AC_PROSE_DEMOTED in log records: {[r.message for r in caplog.records]}"

    def test_emits_log_with_none_feature_id(self, caplog):
        """log_integration_ac_prose_demoted works when feature_id is None."""
        from bob.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        with caplog.at_level(logging.INFO, logger="bob.verification.integration_demotion"):
            log_integration_ac_prose_demoted("integration: foo route through bar", None, [])

        assert any(
            "INTEGRATION_AC_PROSE_DEMOTED" in record.message
            for record in caplog.records
        )

    def test_log_contains_criterion_and_candidates(self, caplog):
        """The log record body contains criterion and scanned_candidates."""
        from bob.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        criterion = "integration: all passes must route through bob.checker"
        candidates = ["bob.checker"]

        with caplog.at_level(logging.INFO, logger="bob.verification.integration_demotion"):
            log_integration_ac_prose_demoted(criterion, "feat-abc", candidates)

        # At least one record should contain JSON with the criterion
        for record in caplog.records:
            try:
                data = json.loads(record.message)
                if data.get("event") == "INTEGRATION_AC_PROSE_DEMOTED":
                    assert data["criterion"] == criterion
                    assert data["scanned_candidates"] == candidates
                    break
            except (json.JSONDecodeError, KeyError):
                continue
        else:
            pytest.fail("No INTEGRATION_AC_PROSE_DEMOTED JSON log record found")


class TestModulePublicApi:
    """Tests that the module exposes its documented public API."""

    def test_extract_integration_targets_callable(self):
        from bob.verification.integration_ac_resolver import extract_integration_targets
        assert callable(extract_integration_targets)

    def test_resolve_integration_ac_callable(self):
        from bob.verification.integration_ac_resolver import resolve_integration_ac
        assert callable(resolve_integration_ac)

    def test_log_integration_ac_prose_demoted_callable(self):
        from bob.verification.integration_ac_resolver import log_integration_ac_prose_demoted
        assert callable(log_integration_ac_prose_demoted)
