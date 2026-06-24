"""Tests for prose AC demotion via _check_criterion_with_details — F-R7-576.

Verifies two key properties:
1. A criterion with NO recognized structural marker and content matching
   the b6873bac patterns passes-with-demotion (counter-test).
2. A structural criterion ("File exists: nonexistent.py") still hard-fails
   after the change (counter-counter-test).

These tests exercise the integration between _check_criterion_with_details
and is_executable_or_structural_criterion in bob.enhanced_verification.
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from bob.enhanced_verification import (
    _check_criterion_with_details,
    is_executable_or_structural_criterion,
)


def _call(criterion: str, tmp_path: pathlib.Path) -> tuple[bool, str]:
    return _check_criterion_with_details(
        criterion=criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestProseAcDemotionViaCheckCriterionWithDetails:
    """Counter-tests: prose ACs pass-with-demotion; structural ACs still hard-fail."""

    def test_b6873bac_prose_pattern_passes_with_demotion(self, tmp_path):
        """A criterion with NO recognized marker and b6873bac content passes-with-demotion."""
        criterion = (
            "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
            "spawn_with_retry — grep guard: no remaining direct `claude --` subprocess "
            "calls outside spawn_retry.py"
        )
        # Pre-condition: this is not a structural criterion
        assert is_executable_or_structural_criterion(criterion) is False

        passed, details = _call(criterion, tmp_path)
        assert passed is True, f"Expected prose AC to pass-with-demotion, got: {details!r}"
        assert "prose AC demoted to warning" in details

    def test_transient_retries_prose_pattern_passes_with_demotion(self, tmp_path):
        """Another b6873bac-pattern prose AC passes-with-demotion."""
        criterion = (
            "Transient retries do NOT increment refinement_attempts, "
            "bootstrap_attempts, verification_failures, or research_iterations "
            "in any pipeline stage"
        )
        assert is_executable_or_structural_criterion(criterion) is False

        passed, details = _call(criterion, tmp_path)
        assert passed is True
        assert "prose AC demoted to warning" in details

    def test_mid_work_crash_prose_pattern_passes_with_demotion(self, tmp_path):
        """Third b6873bac-pattern prose AC (duration_ms==0 reclassify) passes-with-demotion.

        This criterion contains 'F-R6-300' which may trigger a cross-feature-reference
        fallback path instead of the prose-demotion path. Either way the criterion must
        PASS (not hard-fail), which is the invariant F-R7-576 enforces.
        """
        criterion = (
            "Mid-work-crash still counts as one refinement attempt (preserves F-R6-300 behavior), "
            "EXCEPT when duration_ms==0 — that signature is a JSONL serialization race / SIGPIPE / "
            "orphan process pattern, not a sub-agent decision to abort; reclassify as TRANSIENT"
        )
        assert is_executable_or_structural_criterion(criterion) is False

        passed, details = _call(criterion, tmp_path)
        # Must pass — either via prose-demotion or cross-feature-reference fallback
        assert passed is True, (
            f"Expected prose/reference AC to pass (any demotion path), "
            f"got passed={passed!r}, details={details!r}"
        )

    def test_structural_file_exists_nonexistent_still_hard_fails(self, tmp_path):
        """Counter-counter-test: 'File exists: nonexistent.py' still hard-fails after the change."""
        criterion = "File exists: nonexistent_file_that_does_not_exist.py"
        # Pre-condition: this IS a structural criterion
        assert is_executable_or_structural_criterion(criterion) is True

        passed, details = _call(criterion, tmp_path)
        assert passed is False, (
            f"Structural 'File exists:' criterion must hard-fail for missing file, "
            f"got passed={passed!r}, details={details!r}"
        )

    def test_function_defined_nonexistent_still_hard_fails(self, tmp_path):
        """'Function defined:' for a nonexistent function still hard-fails."""
        criterion = "Function defined: bob.totally_nonexistent_module_xyz.nonexistent_func"
        assert is_executable_or_structural_criterion(criterion) is True

        passed, details = _call(criterion, tmp_path)
        assert passed is False, (
            f"Structural 'Function defined:' criterion must hard-fail for missing function, "
            f"got passed={passed!r}, details={details!r}"
        )

    def test_demotion_logged_as_prose_ac_demoted_event(self, tmp_path, caplog):
        """Demoted prose AC emits a PROSE_AC_DEMOTED log event."""
        criterion = "EVERY sub-agent invocation must route through the retry wrapper"
        assert is_executable_or_structural_criterion(criterion) is False

        with caplog.at_level(logging.INFO, logger="bob.verification.prose_demotion"):
            passed, details = _call(criterion, tmp_path)

        assert passed is True
        # Find the PROSE_AC_DEMOTED log record
        demoted_records = [
            r for r in caplog.records
            if r.name == "bob.verification.prose_demotion"
        ]
        assert demoted_records, "Expected at least one PROSE_AC_DEMOTED log record"
        data = json.loads(demoted_records[-1].getMessage())
        assert data["event"] == "PROSE_AC_DEMOTED"
        assert data["criterion"] == criterion

    def test_is_executable_or_structural_criterion_importable_from_enhanced_verification(self):
        """is_executable_or_structural_criterion is accessible via bob.enhanced_verification."""
        from bob.enhanced_verification import is_executable_or_structural_criterion as fn
        assert callable(fn)
        # Spot-check: structural criterion
        assert fn("pytest: tests/foo.py") is True
        # Spot-check: prose criterion
        assert fn("EVERY sub-agent does something") is False

    def test_check_criterion_with_details_importable_from_enhanced_verification(self):
        """_check_criterion_with_details is accessible via bob.enhanced_verification."""
        from bob.enhanced_verification import _check_criterion_with_details as fn
        assert callable(fn)
