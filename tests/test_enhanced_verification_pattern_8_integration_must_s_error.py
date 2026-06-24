"""Error-path tests for Pattern 8 integration AC handler.

Feature bde55fc0-2023-46ce-98f0-4de4125824df:
Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens in body AND
demote prose-policy integration ACs to warning.

This file tests invalid input handling: functions must raise ValueError (or TypeError)
for invalid inputs and must NOT silently succeed.
"""

from __future__ import annotations

import pathlib

import pytest


class TestErrorPathInputs:
    """Invalid inputs must raise and not silently succeed."""

    def test_resolve_non_string_criterion_raises(self, tmp_path):
        """resolve_integration_ac with non-string criterion must raise."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        with pytest.raises((TypeError, ValueError)):
            resolve_integration_ac(123, tmp_path)  # type: ignore[arg-type]

    def test_resolve_none_criterion_raises(self, tmp_path):
        """resolve_integration_ac with None criterion must raise."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        with pytest.raises((TypeError, ValueError)):
            resolve_integration_ac(None, tmp_path)  # type: ignore[arg-type]

    def test_resolve_list_criterion_raises(self, tmp_path):
        """resolve_integration_ac with list criterion must raise."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        with pytest.raises((TypeError, ValueError)):
            resolve_integration_ac(["integration: bob.x"], tmp_path)  # type: ignore[arg-type]

    def test_extract_non_string_criterion_returns_empty(self):
        """extract_integration_targets with non-string returns [] (not raises)."""
        from bob.verification.integration_ac_resolver import extract_integration_targets

        # extract_integration_targets is documented to return [] for non-strings
        result = extract_integration_targets(None)  # type: ignore[arg-type]
        assert result == []

        result = extract_integration_targets(42)  # type: ignore[arg-type]
        assert result == []

    def test_unwired_single_dotted_returns_false_not_silently_passes(self, tmp_path):
        """A single bad dotted token must return (False, ...) not silently pass."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: bob.totally.nonexistent.xyz"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        # Must explicitly reject — not silently succeed
        assert not passed, (
            f"Non-existent dotted module must return False; got passed={passed!r} reason={reason!r}"
        )
        assert isinstance(reason, str)
        assert len(reason) > 0, "reason must not be empty on failure"

    def test_resolve_returns_false_with_reason_on_failure(self, tmp_path):
        """When resolution fails, reason string must be non-empty."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: completely.made.up.nonexistent.path.xyz"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        if not passed:
            assert isinstance(reason, str)
            assert len(reason) > 0, "reason must describe the failure, not be empty"

    def test_resolve_result_is_always_tuple_of_bool_and_str(self, tmp_path):
        """Return type must always be (bool, str) regardless of input."""
        from bob.verification.integration_ac_resolver import resolve_integration_ac

        for criterion in [
            "integration: bob.totally.fake.module",
            "integration:",
            "something: no integration marker",
            "",
        ]:
            if not isinstance(criterion, str):
                continue
            result = resolve_integration_ac(criterion, tmp_path)
            assert isinstance(result, tuple), f"Expected tuple, got {type(result)} for {criterion!r}"
            assert len(result) == 2, f"Expected 2-tuple, got len={len(result)} for {criterion!r}"
            passed, reason = result
            assert isinstance(passed, bool), f"First element must be bool for {criterion!r}"
            assert isinstance(reason, str), f"Second element must be str for {criterion!r}"

    def test_log_integration_ac_prose_demoted_does_not_silently_fail(self, caplog):
        """log_integration_ac_prose_demoted must emit a log line even for unusual inputs."""
        import logging
        from bob.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        # Unusual but valid inputs
        with caplog.at_level(logging.INFO, logger="bob.verification.integration_demotion"):
            log_integration_ac_prose_demoted("integration: foo through bar", "feat-xyz", ["foo"])

        assert any(
            "INTEGRATION_AC_PROSE_DEMOTED" in record.message
            for record in caplog.records
        ), "Must emit INTEGRATION_AC_PROSE_DEMOTED log for valid inputs"
