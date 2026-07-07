"""Prose-AC demotion tests — F-R7-576 runtime closure.

Covers the b6873bac respinning defect: pure-prose acceptance criteria that the
static verifier cannot check MUST pass-with-demotion instead of hard-failing,
while genuinely structural criteria ("File exists: nonexistent.py") MUST still
hard-fail.

Counter-test        : a prose AC matching a b6873bac pattern passes-with-demotion.
Counter-counter test: a structural AC pointing at a missing file still fails.
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from bob.enhanced_verification import _check_criterion_with_details
from bob.verification.prose_ac_demotion import (
    demote_prose_ac,
    is_executable_or_structural_criterion,
    log_prose_ac_demoted,
)


# The exact prose ACs that burned 3 refinement attempts on feature b6873bac.
B6873BAC_PROSE_ACS = [
    (
        "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
        "spawn_with_retry — grep guard: no remaining direct `claude --` "
        "subprocess calls outside spawn_retry.py"
    ),
    (
        "Transient retries do NOT increment refinement_attempts, "
        "bootstrap_attempts, verification_failures, or research_iterations in "
        "any pipeline stage"
    ),
    (
        "Mid-work-crash still counts as one refinement attempt (preserves "
        "F-R6-300 behavior), EXCEPT when duration_ms==0 — that signature is a "
        "JSONL serialization race / SIGPIPE / orphan process pattern, not a "
        "sub-agent decision to abort; reclassify as TRANSIENT"
    ),
]


def _call(criterion: str, tmp_path: pathlib.Path) -> tuple[bool, str]:
    return _check_criterion_with_details(
        criterion=criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestIsExecutableOrStructuralCriterion:
    """The router-level classifier that gates demotion."""

    def test_prose_ac_is_not_structural(self):
        for prose in B6873BAC_PROSE_ACS:
            assert is_executable_or_structural_criterion(prose) is False, prose

    def test_pytest_prefix_is_structural(self):
        assert is_executable_or_structural_criterion("pytest: tests/test_x.py") is True

    def test_file_exists_prefix_is_structural(self):
        assert is_executable_or_structural_criterion("File exists: src/foo.py") is True

    def test_function_defined_prefix_is_structural(self):
        assert is_executable_or_structural_criterion("Function defined: mod.fn") is True

    def test_substring_marker_is_structural(self):
        assert is_executable_or_structural_criterion(
            "the parser function implemented correctly"
        ) is True

    def test_non_string_is_not_structural(self):
        assert is_executable_or_structural_criterion(None) is False
        assert is_executable_or_structural_criterion(42) is False


class TestProseACPassesWithDemotion:
    """Counter-test: prose ACs the verifier cannot check pass-with-demotion."""

    def test_b6873bac_prose_acs_do_not_hard_fail(self, tmp_path):
        """Every b6873bac prose AC ships (passes) instead of gate-blocking.

        Some route through the prose-demotion path, others through the
        cross-feature-reference fallback (F-R7-589) — either way the feature
        must not respin on lines the static verifier cannot check.
        """
        for prose in B6873BAC_PROSE_ACS:
            passed, _ = _call(prose, tmp_path)
            assert passed is True, f"prose AC should not hard-fail: {prose}"

    def test_pure_prose_ac_carries_demotion_marker(self, tmp_path):
        """A prose AC with no feature reference passes with the demotion marker."""
        prose = (
            "Transient retries do NOT increment refinement_attempts, "
            "bootstrap_attempts, verification_failures, or research_iterations "
            "in any pipeline stage"
        )
        passed, details = _call(prose, tmp_path)
        assert passed is True
        assert "demoted" in details.lower(), details

    def test_demote_prose_ac_returns_passing_tuple(self):
        passed, details = demote_prose_ac("some unverifiable prose policy")
        assert passed is True
        assert isinstance(details, str)
        assert "demoted" in details.lower()


class TestStructuralACStillHardFails:
    """Counter-counter test: structural ACs are NOT demoted — they still fail."""

    def test_file_exists_missing_file_hard_fails(self, tmp_path):
        passed, _ = _call("File exists: nonexistent.py", tmp_path)
        assert passed is False

    def test_pytest_missing_test_hard_fails(self, tmp_path):
        passed, _ = _call("pytest: tests/does_not_exist.py", tmp_path)
        assert passed is False

    def test_function_defined_missing_hard_fails(self, tmp_path):
        passed, _ = _call(
            "Function defined: totally.absent.module.function", tmp_path
        )
        assert passed is False


class TestStructuralPassStillPasses:
    """A structural AC pointing at a real file must pass (not spuriously fail)."""

    def test_file_exists_real_file_passes(self, tmp_path):
        (tmp_path / "present.py").write_text("x = 1\n")
        passed, _ = _call("File exists: present.py", tmp_path)
        assert passed is True


class TestLogProseACDemoted:
    """Demotions emit a structured, auditable PROSE_AC_DEMOTED log line."""

    def test_emits_prose_ac_demoted_event(self, caplog):
        with caplog.at_level(logging.INFO, logger="bob.verification.prose_demotion"):
            log_prose_ac_demoted("some prose policy", feature_id="feat-123")
        assert len(caplog.records) == 1
        payload = json.loads(caplog.records[0].getMessage())
        assert payload["event"] == "PROSE_AC_DEMOTED"
        assert payload["criterion"] == "some prose policy"
        assert payload["feature_id"] == "feat-123"
        assert "timestamp" in payload
