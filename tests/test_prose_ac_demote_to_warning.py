"""Prose-AC demote-to-warning tests — F-R7-576 runtime closure.

Feature 9334df7a: _check_criterion_with_details MUST demote pure-prose AC
failures to a pass-with-warning instead of hard-failing the feature. This is
the runtime side of the b6873bac defect where 9/28 pure-policy-prose criteria
("EVERY Claude-CLI sub-agent invocation…", "Transient retries do NOT increment…")
hard-failed verification across three refinement attempts even though every
structural AC passed.

Two guarantees are exercised:

  * Counter-test — a criterion with NO recognized structural/executable marker
    whose text matches one of the b6873bac patterns passes WITH a demotion
    marker (does not hard-fail).
  * Counter-counter-test — a genuine structural criterion ("File exists:
    nonexistent.py") still hard-fails, so demotion never leaks into checks the
    verifier CAN perform statically.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob.enhanced_verification import (
    _check_criterion_with_details,
    is_executable_or_structural_criterion,
)


# The literal b6873bac prose criteria that burned three refinement attempts.
# None of these carry an executable/structural marker, so none may hard-fail.
B6873BAC_PROSE_CRITERIA = [
    "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
    "spawn_with_retry — grep guard: no remaining direct `claude --` subprocess "
    "calls outside spawn_retry.py",
    "Transient retries do NOT increment refinement_attempts, bootstrap_attempts, "
    "verification_failures, or research_iterations in any pipeline stage",
    "Mid-work-crash still counts as one refinement attempt (preserves F-R6-300 "
    "behavior), EXCEPT when duration_ms==0 — that signature is a JSONL "
    "serialization race / SIGPIPE / orphan process pattern, not a sub-agent "
    "decision to abort; reclassify as TRANSIENT",
]

# Prose criteria that carry no cross-feature reference, so they route through
# the demotion path specifically (and thus surface the demotion marker).
DEMOTED_PROSE_CRITERIA = [
    "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
    "spawn_with_retry — grep guard: no remaining direct `claude --` subprocess "
    "calls outside spawn_retry.py",
    "Transient retries do NOT increment refinement_attempts, bootstrap_attempts, "
    "verification_failures, or research_iterations in any pipeline stage",
]

DEMOTION_MARKER = "demoted to warning"


def _check(criterion: str, tmp_path: pathlib.Path) -> tuple[bool, str]:
    return _check_criterion_with_details(
        criterion=criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestProseCriteriaDemoteToWarning:
    """Counter-test: pure-prose criteria pass with a demotion marker."""

    @pytest.mark.parametrize("criterion", B6873BAC_PROSE_CRITERIA)
    def test_b6873bac_prose_criterion_does_not_hard_fail(self, criterion, tmp_path):
        """No pure-prose b6873bac criterion may hard-fail the feature."""
        passed, _ = _check(criterion, tmp_path)
        assert passed is True, f"prose criterion hard-failed: {criterion!r}"

    @pytest.mark.parametrize("criterion", DEMOTED_PROSE_CRITERIA)
    def test_b6873bac_prose_criterion_passes_with_demotion(self, criterion, tmp_path):
        passed, details = _check(criterion, tmp_path)
        assert passed is True, f"prose criterion hard-failed: {criterion!r}"
        assert DEMOTION_MARKER in details.lower(), (
            f"missing demotion marker in details: {details!r}"
        )

    @pytest.mark.parametrize("criterion", B6873BAC_PROSE_CRITERIA)
    def test_b6873bac_prose_criterion_is_not_executable_or_structural(self, criterion):
        assert is_executable_or_structural_criterion(criterion) is False

    def test_generic_prose_criterion_demotes(self, tmp_path):
        passed, details = _check(
            "The system should gracefully recover from transient failures", tmp_path
        )
        assert passed is True
        assert DEMOTION_MARKER in details.lower()


class TestStructuralCriteriaStillHardFail:
    """Counter-counter-test: structural criteria must NOT be demoted."""

    def test_missing_file_exists_hard_fails(self, tmp_path):
        passed, _ = _check("File exists: nonexistent.py", tmp_path)
        assert passed is False

    def test_missing_function_defined_hard_fails(self, tmp_path):
        passed, _ = _check(
            "Function defined: bob.does_not_exist.no_such_function", tmp_path
        )
        assert passed is False

    def test_present_file_exists_passes_without_demotion(self, tmp_path):
        (tmp_path / "present.py").write_text("x = 1\n")
        passed, details = _check("File exists: present.py", tmp_path)
        assert passed is True
        assert DEMOTION_MARKER not in details.lower()


class TestDemotionIsLogged:
    """The verifier emits a PROSE_AC_DEMOTED event per demoted criterion."""

    def test_prose_demotion_emits_prose_ac_demoted_event(self, tmp_path, caplog):
        with caplog.at_level(logging.INFO, logger="bob.verification.prose_demotion"):
            passed, details = _check(B6873BAC_PROSE_CRITERIA[0], tmp_path)
        assert passed is True
        assert any("PROSE_AC_DEMOTED" in rec.getMessage() for rec in caplog.records), (
            "expected a PROSE_AC_DEMOTED log line for the demoted criterion"
        )

    def test_structural_failure_does_not_emit_demotion_event(self, tmp_path, caplog):
        with caplog.at_level(logging.INFO, logger="bob.verification.prose_demotion"):
            _check("File exists: nonexistent.py", tmp_path)
        assert not any(
            "PROSE_AC_DEMOTED" in rec.getMessage() for rec in caplog.records
        )
