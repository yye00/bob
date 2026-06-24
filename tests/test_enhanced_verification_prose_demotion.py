"""Tests for prose AC demotion — F-R7-576.

Verifies that:
1. is_executable_or_structural_criterion correctly classifies criteria
2. _check_criterion_with_details demotes pure-prose ACs to warning instead of
   hard-failing (the b6873bac pattern)
3. Structural criteria ("File exists: ...") still hard-fail correctly
4. PROSE_AC_DEMOTED log events are emitted for each demoted criterion
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from bob3.enhanced_verification import _check_criterion_with_details
from bob3.verification.prose_ac_demotion import (
    demote_prose_ac,
    is_executable_or_structural_criterion,
    log_prose_ac_demoted,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_with_details(criterion: str, tmp_path: pathlib.Path) -> tuple[bool, str]:
    return _check_criterion_with_details(
        criterion=criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


# ---------------------------------------------------------------------------
# Tests for is_executable_or_structural_criterion
# ---------------------------------------------------------------------------

class TestIsExecutableOrStructuralCriterion:
    """Unit tests for the is_executable_or_structural_criterion helper."""

    # Structural prefix criteria — must return True
    @pytest.mark.parametrize("criterion", [
        "pytest: tests/test_foo.py",
        "python: import bob3; assert hasattr(bob3, 'foo')",
        "CI tests: 5 golden specs",
        "ci tests: some description",
        "forbidden_imports: subprocess",
        "behavioral_signature: command=python -m bob3",
        "deterministic_output: command=echo hello",
        "resource_limit: peak_mem_mb=100 command=echo",
        "test_coupling: check",
        "mms: ...",
        "conserves: energy",
        "File exists: src/bob3/foo.py",
        "file exists: some/path.py",
        "Function defined: bob3.foo.bar",
        "function defined: module.func",
        "Class defined: bob3.Foo",
        "class defined: mymodule.MyClass",
        "integration: bob3.some_module",
    ])
    def test_structural_criterion_returns_true(self, criterion):
        assert is_executable_or_structural_criterion(criterion) is True

    # Substring markers — must also return True
    @pytest.mark.parametrize("criterion", [
        "This function implemented in module X",
        "The method implemented by the class",
        "cmake build target added",
        "no compilation errors after change",
        "No errors in the output",
    ])
    def test_substring_marker_criterion_returns_true(self, criterion):
        assert is_executable_or_structural_criterion(criterion) is True

    # Pure prose — must return False
    @pytest.mark.parametrize("criterion", [
        "EVERY Claude-CLI sub-agent invocation in the codebase routes through spawn_with_retry",
        "Transient retries do NOT increment refinement_attempts, bootstrap_attempts, verification_failures",
        "Mid-work-crash still counts as one refinement attempt",
        "The orchestrator must handle network timeouts gracefully",
        "All pipeline stages preserve the feature budget",
        "feature ships permanent features instead of attempt-budget-cycling on prose lines",
        "no remaining direct claude -- subprocess calls outside spawn_retry.py",
        "reclassify as TRANSIENT when duration_ms==0",
    ])
    def test_pure_prose_criterion_returns_false(self, criterion):
        assert is_executable_or_structural_criterion(criterion) is False

    def test_behavior_prefix_returns_false(self):
        """criteria starting with 'behavior:' are always prose, never executable."""
        assert is_executable_or_structural_criterion("behavior: foo returns 'no errors'") is False

    def test_behavior_prefix_with_quoted_pytest_returns_false(self):
        """behavior: prefix overrides any structural marker in body."""
        assert is_executable_or_structural_criterion("behavior: contains 'pytest:' in message") is False

    def test_non_string_returns_false(self):
        assert is_executable_or_structural_criterion(None) is False
        assert is_executable_or_structural_criterion(42) is False
        assert is_executable_or_structural_criterion([]) is False

    def test_mid_sentence_pytest_quote_returns_false(self):
        """Quoting 'pytest:' mid-sentence must NOT trigger structural classification."""
        assert is_executable_or_structural_criterion(
            "This criterion quotes 'pytest:' but is not executable"
        ) is False

    def test_empty_string_returns_false(self):
        assert is_executable_or_structural_criterion("") is False


# ---------------------------------------------------------------------------
# Counter-test: b6873bac prose patterns pass-with-demotion
# (the core fix from F-R7-576)
# ---------------------------------------------------------------------------

class TestProseDemotionCounterTest:
    """Counter-test: criteria with NO recognized structural marker + b6873bac
    content must pass with a demotion marker, not hard-fail.

    These are the exact patterns that caused feature b6873bac to respin 3 times.
    """

    @pytest.mark.parametrize("criterion", [
        "EVERY Claude-CLI sub-agent invocation in the codebase routes through spawn_with_retry — grep guard: no remaining direct claude subprocess calls outside spawn_retry.py",
        "Transient retries do NOT increment refinement_attempts, bootstrap_attempts, verification_failures, or research_iterations in any pipeline stage",
        "feature ships on structural ACs and the prose warning is surfaced for human review without blocking forward progress",
        "The orchestrator must route all calls through the approved wrapper layer",
        "Pipeline stages MUST NOT bypass the cost ceiling enforcement gate",
    ])
    def test_b6873bac_prose_pattern_passes_with_demotion(self, criterion, tmp_path):
        """A prose criterion matching b6873bac patterns must pass (either demoted or
        via another prose-pass mechanism), not hard-fail.
        """
        passed, details = _call_with_details(criterion, tmp_path)
        assert passed is True, (
            f"Expected prose AC to pass (demoted or otherwise), got pass={passed!r} for: {criterion!r}"
        )

    def test_generic_prose_criterion_passes_with_demotion(self, tmp_path):
        """Any plain prose criterion without structural markers is demoted."""
        criterion = "The orchestrator must gracefully handle transient failures"
        passed, details = _call_with_details(criterion, tmp_path)
        assert passed is True
        assert "demoted" in details.lower() or "prose" in details.lower()

    def test_demotion_message_contains_forward_carry_marker(self, tmp_path):
        """Demotion reason must reference F-R7-531 forward-carry."""
        criterion = "EVERY sub-agent call routes through the retry wrapper"
        passed, details = _call_with_details(criterion, tmp_path)
        assert passed is True
        assert "F-R7-531" in details or "forward-carry" in details


# ---------------------------------------------------------------------------
# Counter-counter-test: structural criterion still hard-fails
# ---------------------------------------------------------------------------

class TestStructuralCriterionHardFails:
    """Counter-counter-test: structural criteria still hard-fail even after
    the prose-demotion logic is in place.
    """

    def test_file_exists_nonexistent_hard_fails(self, tmp_path):
        """'File exists: nonexistent.py' must hard-fail, not be demoted."""
        passed, details = _call_with_details("File exists: nonexistent.py", tmp_path)
        assert passed is False, (
            "Expected structural 'File exists:' to hard-fail for a missing file"
        )

    def test_function_defined_missing_module_hard_fails(self, tmp_path):
        """'Function defined:' for a non-existent module must hard-fail."""
        passed, details = _call_with_details(
            "Function defined: bob3.nonexistent_module_xyz.some_func",
            tmp_path,
        )
        assert passed is False, (
            "Expected structural 'Function defined:' to hard-fail for missing module"
        )

    def test_file_exists_for_existing_file_passes(self, tmp_path):
        """'File exists:' for an actual file (relative path) must pass normally."""
        real_file = tmp_path / "real_file.py"
        real_file.write_text("# real")
        passed, details = _call_with_details("File exists: real_file.py", tmp_path)
        assert passed is True

    def test_structural_fails_are_not_demoted(self, tmp_path):
        """Structural failures must NOT contain a demotion marker."""
        passed, details = _call_with_details("File exists: totally_missing.py", tmp_path)
        assert passed is False
        # details should not say 'demoted'
        assert "demoted" not in details.lower()


# ---------------------------------------------------------------------------
# Tests for demote_prose_ac helper directly
# ---------------------------------------------------------------------------

class TestDemoteProseAc:
    """Unit tests for the demote_prose_ac helper."""

    def test_returns_tuple(self):
        result = demote_prose_ac("some prose criterion")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_true(self):
        passed, details = demote_prose_ac("some prose criterion")
        assert passed is True

    def test_demotion_details_mention_f_r7_531(self):
        passed, details = demote_prose_ac("any prose")
        assert "F-R7-531" in details

    def test_demotion_details_mention_prose(self):
        passed, details = demote_prose_ac("any prose")
        assert "prose" in details.lower()


# ---------------------------------------------------------------------------
# Tests for log_prose_ac_demoted — PROSE_AC_DEMOTED event emission
# ---------------------------------------------------------------------------

class TestLogProseAcDemoted:
    """Verify that log_prose_ac_demoted writes a PROSE_AC_DEMOTED JSON event."""

    def test_emits_log_record(self, caplog):
        criterion = "EVERY sub-agent routes through spawn_with_retry"
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted(criterion, feature_id="test-feature-id")
        assert len(caplog.records) >= 1

    def test_log_record_is_valid_json(self, caplog):
        criterion = "All pipeline stages preserve the feature budget"
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted(criterion, feature_id="feat-abc")
        record = caplog.records[-1]
        data = json.loads(record.message)
        assert data["event"] == "PROSE_AC_DEMOTED"
        assert data["criterion"] == criterion
        assert data["feature_id"] == "feat-abc"

    def test_log_record_has_timestamp(self, caplog):
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted("some prose", feature_id=None)
        data = json.loads(caplog.records[-1].message)
        assert "timestamp" in data
        assert data["timestamp"]  # non-empty

    def test_log_record_feature_id_none(self, caplog):
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted("prose criterion", feature_id=None)
        data = json.loads(caplog.records[-1].message)
        assert data["feature_id"] is None

    def test_check_criterion_with_details_emits_log_on_demotion(self, tmp_path, caplog):
        """When _check_criterion_with_details demotes a prose AC, it must log."""
        criterion = "EVERY sub-agent routes through spawn_with_retry"
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            _call_with_details(criterion, tmp_path)
        demoted_records = [
            r for r in caplog.records
            if "PROSE_AC_DEMOTED" in r.message
        ]
        assert len(demoted_records) >= 1, (
            "Expected at least one PROSE_AC_DEMOTED log event from demotion"
        )

    def test_structural_criterion_does_not_emit_demoted_log(self, tmp_path, caplog):
        """Structural failures must NOT emit a PROSE_AC_DEMOTED log."""
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            _call_with_details("File exists: nonexistent_xyz.py", tmp_path)
        demoted_records = [
            r for r in caplog.records
            if "PROSE_AC_DEMOTED" in r.message
        ]
        assert len(demoted_records) == 0, (
            "Structural failure must not emit PROSE_AC_DEMOTED log"
        )


# ---------------------------------------------------------------------------
# Integration: bob3.enhanced_verification imports prose_ac_demotion
# ---------------------------------------------------------------------------

class TestIntegrationEnhancedVerification:
    """Verify the integration between enhanced_verification and prose_ac_demotion."""

    def test_is_executable_or_structural_criterion_importable_from_enhanced_verification(self):
        """is_executable_or_structural_criterion is accessible from enhanced_verification."""
        from bob3.enhanced_verification import is_executable_or_structural_criterion as f
        assert callable(f)

    def test_check_criterion_with_details_importable(self):
        from bob3.enhanced_verification import _check_criterion_with_details as f
        assert callable(f)

    def test_enhanced_verification_module_imports_prose_demotion(self):
        """The enhanced_verification module must import from prose_ac_demotion."""
        import bob3.enhanced_verification as ev
        import inspect
        src = inspect.getsource(ev)
        assert "prose_ac_demotion" in src, (
            "enhanced_verification.py must import from bob3.verification.prose_ac_demotion"
        )

    def test_demotion_passes_through_validate_acceptance_criteria(self, tmp_path):
        """validate_acceptance_criteria must demote prose ACs (not hard-fail)."""
        from bob3.enhanced_verification import validate_acceptance_criteria
        criteria = [
            "EVERY Claude-CLI sub-agent invocation routes through spawn_with_retry",
            "Transient retries do NOT increment refinement_attempts",
        ]
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=criteria,
            is_python_project=True,
        )
        assert passed is True, (
            f"validate_acceptance_criteria should pass when all ACs are prose (demoted), got: {details}"
        )
