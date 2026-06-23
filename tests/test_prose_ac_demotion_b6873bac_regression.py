"""Regression tests for b6873bac prose AC demotion via validate_acceptance_criteria.

Guards two invariants:
1. Prose criteria (no structural marker) pass-with-demotion → PROSE_AC_DEMOTED logged.
2. Structural criteria ("File exists: …") still hard-fail when the file is absent.
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from bob3.enhanced_verification import validate_acceptance_criteria


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_demotion_records(caplog: pytest.LogCaptureFixture) -> list[dict]:
    """Extract all PROSE_AC_DEMOTED log records emitted during the test."""
    records = []
    for r in caplog.records:
        try:
            data = json.loads(r.getMessage())
            if data.get("event") == "PROSE_AC_DEMOTED":
                records.append(data)
        except (json.JSONDecodeError, AttributeError):
            pass
    return records


# ---------------------------------------------------------------------------
# Test 1: prose criterion passes-with-demotion
# ---------------------------------------------------------------------------

class TestProseAcDemotionPassesWithWarning:
    """b6873bac prose ACs must no longer gate-block the feature."""

    @pytest.mark.parametrize("prose_criterion", [
        (
            "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
            "spawn_with_retry — grep guard: no remaining direct `claude --` subprocess "
            "calls outside spawn_retry.py"
        ),
        (
            "Transient retries do NOT increment refinement_attempts, "
            "bootstrap_attempts, verification_failures, or research_iterations "
            "in any pipeline stage (planning, spec-extraction, implementation, "
            "verification, evaluation, research, RCA)"
        ),
        (
            "Retry storm (>20 retries in 10min for one feature) emits WARN event "
            "but does NOT halt or fail the feature"
        ),
    ])
    def test_prose_ac_passes_with_demotion(
        self,
        prose_criterion: str,
        tmp_path: pathlib.Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            passed, details = validate_acceptance_criteria(
                workspace=tmp_path,
                acceptance_criteria=[prose_criterion],
                is_python_project=True,
            )

        assert passed is True, (
            f"Prose AC must pass-with-demotion, but got failed=True with details: {details!r}"
        )

        demotions = _collect_demotion_records(caplog)
        assert len(demotions) >= 1, (
            "Expected at least one PROSE_AC_DEMOTED log event but none was emitted"
        )
        assert demotions[0]["criterion"] == prose_criterion


# ---------------------------------------------------------------------------
# Test 2: structural AC still hard-fails for missing file
# ---------------------------------------------------------------------------

class TestStructuralAcStillHardFails:
    """File exists: pointing at a nonexistent file must still return False."""

    def test_missing_file_ac_fails(self, tmp_path: pathlib.Path) -> None:
        criterion = "File exists: src/does_not_exist.py"

        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[criterion],
            is_python_project=True,
        )

        assert passed is False, (
            "Structural 'File exists:' AC for a missing file must hard-fail, not pass"
        )

    def test_existing_file_ac_passes(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "mymodule.py").write_text("x = 1\n")
        criterion = "File exists: mymodule.py"

        passed, _ = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=[criterion],
            is_python_project=True,
        )

        assert passed is True


# ---------------------------------------------------------------------------
# Test 3: mixed criteria — prose demoted, structural checked accurately
# ---------------------------------------------------------------------------

class TestMixedCriteria:
    def test_mixed_passes_when_file_exists(
        self,
        tmp_path: pathlib.Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        (tmp_path / "real_file.py").write_text("pass\n")

        criteria = [
            "EVERY policy thing that cannot be verified statically",
            "File exists: real_file.py",
        ]

        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            passed, _ = validate_acceptance_criteria(
                workspace=tmp_path,
                acceptance_criteria=criteria,
                is_python_project=True,
            )

        assert passed is True
        demotions = _collect_demotion_records(caplog)
        assert len(demotions) == 1

    def test_mixed_fails_when_file_missing(
        self,
        tmp_path: pathlib.Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        criteria = [
            "EVERY policy thing that cannot be verified statically",
            "File exists: missing_file.py",
        ]

        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            passed, details = validate_acceptance_criteria(
                workspace=tmp_path,
                acceptance_criteria=criteria,
                is_python_project=True,
            )

        assert passed is False
        # The prose AC should still be demoted (logged) even though the overall result fails
        demotions = _collect_demotion_records(caplog)
        assert len(demotions) == 1
