"""Tests for disk_reconciler_promotion_check — F-R7-612 (c0b5aadd).

Verifies that handle_execution_result (and the new public facade
disk_reconciler_promotion_check) attempts disk promotion BEFORE
marking a feature needs_human when verification fails with only
tests_pass failing and structural/behavior ACs present on disk.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(feature_id: str, ac_json: str | None = None) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = "test feature"
    f.acceptance_criteria = ac_json or '["File exists: src/bob/run_loop.py"]'
    f.parent_feature_id = None
    f.project_id = "proj-test-disk-prom"
    f.refinement_attempts = 0
    return f


def _make_spawn_result(is_error: bool = False) -> MagicMock:
    sr = MagicMock()
    sr.execution_result.is_error = is_error
    sr.execution_result.text = "output"
    sr.execution_result.duration_ms = 1000
    sr.execution_result.num_turns = 5
    sr.execution_result.total_cost_usd = 0.10
    sr.execution_result.tool_uses = []
    sr.execution_result.error_message = "" if not is_error else "sub-agent error"
    sr.agent_run = MagicMock()
    sr.agent_run.id = "run-test-disk-prom"
    return sr


def _make_verification_result(tests_pass: bool, structural_passed: bool = True) -> dict:
    checks = [
        {"name": "structural_acs_present", "passed": structural_passed},
        {"name": "tests_pass", "passed": tests_pass, "severity": "error"},
        {"name": "acceptance_criteria_met", "passed": structural_passed},
    ]
    return {
        "passed": tests_pass and structural_passed,
        "summary": "ok" if (tests_pass and structural_passed) else "tests_pass failed",
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Tests for disk_reconciler_promotion_check in bob.run_loop (public facade)
# ---------------------------------------------------------------------------

class TestDiskReconcilerPromotionCheckPublicFacade:
    """Tests that the public facade function exists and is callable."""

    def test_function_defined_in_run_loop_module(self):
        """disk_reconciler_promotion_check must be importable from bob.run_loop."""
        from bob.run_loop import disk_reconciler_promotion_check
        assert callable(disk_reconciler_promotion_check)

    def test_function_in_dunder_all(self):
        """disk_reconciler_promotion_check must appear in bob.run_loop.__all__."""
        import bob.run_loop as m
        assert "disk_reconciler_promotion_check" in m.__all__

    def test_returns_false_when_ac_json_empty(self):
        """Returns False without crashing when AC list is empty."""
        from bob.run_loop import disk_reconciler_promotion_check
        result = disk_reconciler_promotion_check(
            project_id="proj-x",
            feature_id="feat-x",
            feature_name="x",
            acceptance_criteria_json="[]",
        )
        assert result is False

    def test_returns_false_when_ac_json_invalid(self):
        """Returns False without crashing when AC JSON is malformed."""
        from bob.run_loop import disk_reconciler_promotion_check
        result = disk_reconciler_promotion_check(
            project_id="proj-x",
            feature_id="feat-x",
            feature_name="x",
            acceptance_criteria_json="not-json",
        )
        assert result is False

    def test_accepts_optional_failed_gate_parameter(self):
        """disk_reconciler_promotion_check accepts failed_gate kwarg without raising."""
        from bob.run_loop import disk_reconciler_promotion_check
        # Should not raise even if check fails internally
        try:
            disk_reconciler_promotion_check(
                project_id="proj-x",
                feature_id="feat-x",
                feature_name="x",
                acceptance_criteria_json='["File exists: nonexistent_path_xyz.py"]',
                failed_gate="tests_pass",
            )
        except TypeError:
            pytest.fail("disk_reconciler_promotion_check should accept failed_gate kwarg")

    def test_accepts_passed_gates_parameter(self):
        """disk_reconciler_promotion_check accepts passed_gates kwarg without raising."""
        from bob.run_loop import disk_reconciler_promotion_check
        try:
            disk_reconciler_promotion_check(
                project_id="proj-x",
                feature_id="feat-x",
                feature_name="x",
                acceptance_criteria_json='["File exists: nonexistent_path_xyz.py"]',
                passed_gates=["structural"],
            )
        except TypeError:
            pytest.fail("disk_reconciler_promotion_check should accept passed_gates kwarg")

    def test_delegates_to_check_executing_feature_acs(self):
        """disk_reconciler_promotion_check delegates to check_executing_feature_acs."""
        from bob.run_loop import disk_reconciler_promotion_check
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ) as mock_check:
            result = disk_reconciler_promotion_check(
                project_id="proj-delegate",
                feature_id="feat-delegate",
                feature_name="delegate test",
                acceptance_criteria_json='["File exists: src/bob/run_loop.py"]',
            )
        assert result is True
        mock_check.assert_called_once()

    def test_returns_true_when_disk_check_passes(self):
        """Returns True when check_executing_feature_acs returns True."""
        from bob.run_loop import disk_reconciler_promotion_check
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_promotion_check(
                project_id="proj-y",
                feature_id="feat-y",
                feature_name="y",
                acceptance_criteria_json='["File exists: src/bob/run_loop.py"]',
            )
        assert result is True

    def test_returns_false_when_disk_check_fails(self):
        """Returns False when check_executing_feature_acs returns False."""
        from bob.run_loop import disk_reconciler_promotion_check
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=False,
        ):
            result = disk_reconciler_promotion_check(
                project_id="proj-z",
                feature_id="feat-z",
                feature_name="z",
                acceptance_criteria_json='["File exists: src/bob/run_loop.py"]',
            )
        assert result is False


# ---------------------------------------------------------------------------
# Tests for handle_execution_result disk promotion path
# ---------------------------------------------------------------------------

class TestHandleExecutionResultDiskPromotion:
    """Tests that handle_execution_result promotes via disk before marking NH."""

    def test_handle_execution_result_accepts_verification_result_param(self):
        """handle_execution_result must accept a verification_result keyword argument."""
        import inspect
        from bob.orchestrator.run_loop import handle_execution_result
        sig = inspect.signature(handle_execution_result)
        assert "verification_result" in sig.parameters, (
            "handle_execution_result must have a verification_result parameter"
        )

    def test_disk_promote_fires_before_needs_human_when_tests_pass_only_failing(self):
        """When only tests_pass fails and structural ACs are on disk, disk promotes."""
        from bob.orchestrator.run_loop import handle_execution_result
        feature_id = "feat-dp-001-000000000001"
        feature = _make_feature(
            feature_id, '["File exists: src/bob/run_loop.py"]'
        )
        spawn_result = _make_spawn_result(is_error=False)
        verification_result = _make_verification_result(tests_pass=False, structural_passed=True)

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._may_demote", return_value=True), \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs",
                   return_value=True) as mock_check_acs, \
             patch("bob.orchestrator.run_loop._rca_auto_reset_if_infra",
                   return_value=False):
            mock_db.increment_refinement_attempts.return_value = None  # exhausted

            outcome = handle_execution_result(
                project_id="proj-dp-001",
                feature=feature,
                spawn_result=spawn_result,
                verification_passed=False,
                verification_summary="tests_pass failed",
                verification_result=verification_result,
                workspace=str(pathlib.Path.cwd()),
            )

        # Disk promoted → needs_human must NOT be called
        nh_calls = [
            c for c in mock_db.update_feature.call_args_list
            if c.kwargs.get("status") == "needs_human"
            or (len(c.args) > 1 and c.args[1] == "needs_human")
        ]
        assert not nh_calls, (
            f"feature should not be marked needs_human after disk promotion: {nh_calls}"
        )

    def test_needs_human_proceeds_when_disk_check_fails(self):
        """When disk check returns False, feature is marked needs_human."""
        from bob.orchestrator.run_loop import handle_execution_result
        feature_id = "feat-dp-002-000000000002"
        feature = _make_feature(
            feature_id, '["File exists: nonexistent_xyz.py"]'
        )
        spawn_result = _make_spawn_result(is_error=False)
        verification_result = _make_verification_result(tests_pass=False, structural_passed=True)

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._may_demote", return_value=True), \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs",
                   return_value=False) as mock_check_acs, \
             patch("bob.orchestrator.run_loop._rca_auto_reset_if_infra",
                   return_value=False):
            mock_db.increment_refinement_attempts.return_value = None  # exhausted

            outcome = handle_execution_result(
                project_id="proj-dp-002",
                feature=feature,
                spawn_result=spawn_result,
                verification_passed=False,
                verification_summary="tests_pass failed",
                verification_result=verification_result,
                workspace=str(pathlib.Path.cwd()),
            )

        nh_calls = [
            c for c in mock_db.update_feature.call_args_list
            if c.kwargs.get("status") == "needs_human"
            or (len(c.args) > 1 and c.args[1] == "needs_human")
        ]
        assert nh_calls, (
            f"feature should be marked needs_human when disk check fails; "
            f"calls={mock_db.update_feature.call_args_list}"
        )

    def test_no_disk_promote_when_all_gates_fail(self):
        """Guard: no disk promotion when structural ACs are also failing."""
        from bob.orchestrator.run_loop import handle_execution_result
        feature_id = "feat-dp-003-000000000003"
        feature = _make_feature(feature_id, '[]')
        spawn_result = _make_spawn_result(is_error=False)
        # All-gates-failed: structural_passed=False
        verification_result = {
            "passed": False,
            "summary": "all checks failed",
            "checks": [
                {"name": "structural_acs_present", "passed": False},
                {"name": "tests_pass", "passed": False, "severity": "error"},
                {"name": "acceptance_criteria_met", "passed": False},
            ],
        }

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._may_demote", return_value=True), \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs",
                   return_value=True) as mock_check_acs, \
             patch("bob.orchestrator.run_loop._rca_auto_reset_if_infra",
                   return_value=False):
            mock_db.increment_refinement_attempts.return_value = None

            outcome = handle_execution_result(
                project_id="proj-dp-003",
                feature=feature,
                spawn_result=spawn_result,
                verification_passed=False,
                verification_summary="all failed",
                verification_result=verification_result,
                workspace=str(pathlib.Path.cwd()),
            )

        # With empty AC list, structural_count=0 → guard fires → disk promote skipped
        # _check_executing_feature_acs may be called with empty ACs, returns False anyway
        nh_calls = [
            c for c in mock_db.update_feature.call_args_list
            if c.kwargs.get("status") == "needs_human"
            or (len(c.args) > 1 and c.args[1] == "needs_human")
        ]
        assert nh_calls, (
            f"feature should be marked needs_human when all gates fail; "
            f"calls={mock_db.update_feature.call_args_list}"
        )

    def test_backward_compat_no_verification_result_falls_through(self):
        """Old callers that don't pass verification_result still get needs_human."""
        from bob.orchestrator.run_loop import handle_execution_result
        feature_id = "feat-dp-004-000000000004"
        feature = _make_feature(feature_id)
        spawn_result = _make_spawn_result(is_error=False)

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._may_demote", return_value=True), \
             patch("bob.orchestrator.run_loop._rca_auto_reset_if_infra",
                   return_value=False):
            mock_db.increment_refinement_attempts.return_value = None

            # verification_result not passed — old caller pattern
            outcome = handle_execution_result(
                project_id="proj-dp-004",
                feature=feature,
                spawn_result=spawn_result,
                verification_passed=False,
                verification_summary="failed",
                workspace=str(pathlib.Path.cwd()),
            )

        nh_calls = [
            c for c in mock_db.update_feature.call_args_list
            if c.kwargs.get("status") == "needs_human"
            or (len(c.args) > 1 and c.args[1] == "needs_human")
        ]
        assert nh_calls, (
            "feature should be marked needs_human when no verification_result passed"
        )

    def test_no_disk_promote_when_sub_agent_errored(self):
        """Disk promote only fires on verify-fail path, not on sub-agent error path."""
        from bob.orchestrator.run_loop import handle_execution_result
        feature_id = "feat-dp-005-000000000005"
        feature = _make_feature(
            feature_id, '["File exists: src/bob/run_loop.py"]'
        )
        spawn_result = _make_spawn_result(is_error=True)
        verification_result = _make_verification_result(tests_pass=False, structural_passed=True)

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._may_demote", return_value=True), \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs",
                   return_value=True) as mock_check_acs:

            outcome = handle_execution_result(
                project_id="proj-dp-005",
                feature=feature,
                spawn_result=spawn_result,
                verification_passed=False,
                verification_summary="tests_pass failed",
                verification_result=verification_result,
                workspace=str(pathlib.Path.cwd()),
            )

        # is_error=True routes to the error branch, not the verify-fail branch
        completed_calls = [
            c for c in mock_db.update_feature.call_args_list
            if c.kwargs.get("status") == "completed"
            or (len(c.args) > 1 and c.args[1] == "completed")
        ]
        assert not completed_calls, (
            f"feature should not be marked completed when sub-agent errored: {completed_calls}"
        )


# ---------------------------------------------------------------------------
# Tests for VERIFY_FAIL_DISK_PROMOTED event emission
# ---------------------------------------------------------------------------

class TestVerifyFailDiskPromotedEvent:
    """Tests that the VERIFY_FAIL_DISK_PROMOTED event is emitted on promotion."""

    def test_verify_fail_disk_promoted_string_in_orchestrator_run_loop(self):
        """VERIFY_FAIL_DISK_PROMOTED literal must exist in orchestrator run_loop."""
        src = pathlib.Path("src/bob/orchestrator/run_loop.py")
        if not src.exists():
            pytest.skip("orchestrator run_loop not found")
        content = src.read_text()
        assert "VERIFY_FAIL_DISK_PROMOTED" in content, (
            "src/bob/orchestrator/run_loop.py must contain 'VERIFY_FAIL_DISK_PROMOTED'"
        )

    def test_f_r7_612_marker_in_orchestrator_run_loop(self):
        """F-R7-612 feature marker must exist in orchestrator run_loop."""
        src = pathlib.Path("src/bob/orchestrator/run_loop.py")
        if not src.exists():
            pytest.skip("orchestrator run_loop not found")
        content = src.read_text()
        assert "F-R7-612" in content, (
            "src/bob/orchestrator/run_loop.py must contain 'F-R7-612'"
        )

    def test_tests_pass_reference_near_f_r7_612(self):
        """tests_pass string must appear within 300 lines of F-R7-612 in orchestrator run_loop."""
        src = pathlib.Path("src/bob/orchestrator/run_loop.py")
        if not src.exists():
            pytest.skip("orchestrator run_loop not found")
        lines = src.read_text().splitlines()
        fr612_line = next(
            (i + 1 for i, l in enumerate(lines) if "F-R7-612" in l), None
        )
        tp_line = next(
            (i + 1 for i, l in enumerate(lines) if "tests_pass" in l and i > (fr612_line or 0) - 300),
            None,
        )
        assert fr612_line is not None, "F-R7-612 not found in run_loop.py"
        assert tp_line is not None, "tests_pass not found near F-R7-612 in run_loop.py"


# ---------------------------------------------------------------------------
# Guard condition tests
# ---------------------------------------------------------------------------

class TestDiskPromotionGuardCondition:
    """Tests for the (structural_count + behavior_count) > 0 guard."""

    @pytest.mark.parametrize("ac_json,expect_attempted", [
        # Structural ACs present → guard passes → disk check attempted
        ('["File exists: src/bob/run_loop.py"]', True),
        ('["Function defined: bob.run_loop.disk_reconciler_promotion_check"]', True),
        # Integration AC only (counts as structural check) → guard passes
        ('["integration: bob.run_loop"]', True),
        # pytest-only → structural_count=0 → guard may or may not fire (impl detail)
        ('["pytest: tests/test_foo.py"]', None),  # not asserting direction
        # Empty AC list → guard fires immediately (no ACs = no structural = no promote)
        ('[]', False),
    ])
    def test_guard_fires_based_on_ac_types(
        self, ac_json: str, expect_attempted: bool | None, tmp_path: pathlib.Path
    ):
        """Guard condition allows or blocks disk promotion based on AC types."""
        from bob.orchestrator.run_loop import handle_execution_result

        feature = _make_feature("feat-guard-001", ac_json)
        spawn_result = _make_spawn_result(is_error=False)
        verification_result = {
            "passed": False,
            "summary": "tests_pass failed",
            "checks": [
                {"name": "structural_acs_present", "passed": True},
                {"name": "tests_pass", "passed": False},
            ],
        }

        check_acs_called = []

        def fake_check_acs(*args, **kwargs):
            check_acs_called.append(True)
            return False  # always return False to avoid promotion side effects

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._may_demote", return_value=True), \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs",
                   side_effect=fake_check_acs), \
             patch("bob.orchestrator.run_loop._rca_auto_reset_if_infra",
                   return_value=False):
            mock_db.increment_refinement_attempts.return_value = None

            handle_execution_result(
                project_id="proj-guard-001",
                feature=feature,
                spawn_result=spawn_result,
                verification_passed=False,
                verification_summary="tests_pass failed",
                verification_result=verification_result,
                workspace=str(tmp_path),
            )

        if expect_attempted is True:
            assert check_acs_called, (
                f"Expected _check_executing_feature_acs to be called for ACs={ac_json}"
            )
        elif expect_attempted is False:
            assert not check_acs_called, (
                f"Expected _check_executing_feature_acs NOT to be called for ACs={ac_json}"
            )
        # None means we don't assert the direction (impl detail)


# ---------------------------------------------------------------------------
# Integration: bob.run_loop module structure
# ---------------------------------------------------------------------------

class TestRunLoopModuleIntegration:
    """Verify the public bob.run_loop module has the required function."""

    def test_disk_reconciler_promotion_check_importable(self):
        """disk_reconciler_promotion_check must be importable directly."""
        from bob.run_loop import disk_reconciler_promotion_check
        assert disk_reconciler_promotion_check is not None

    def test_disk_reconciler_promotion_check_signature(self):
        """disk_reconciler_promotion_check must have required parameters."""
        import inspect
        from bob.run_loop import disk_reconciler_promotion_check
        sig = inspect.signature(disk_reconciler_promotion_check)
        params = set(sig.parameters.keys())
        assert "project_id" in params
        assert "feature_id" in params
        assert "feature_name" in params
        assert "acceptance_criteria_json" in params

    def test_module_runs_without_error(self):
        """bob.run_loop module imports cleanly."""
        import bob.run_loop  # noqa: F401

    def test_disk_reconciler_promotion_check_never_raises_on_empty_workspace(
        self, tmp_path: pathlib.Path
    ):
        """disk_reconciler_promotion_check returns False on empty workspace without raising."""
        from bob.run_loop import disk_reconciler_promotion_check
        result = disk_reconciler_promotion_check(
            project_id="proj-empty",
            feature_id="feat-empty",
            feature_name="empty workspace test",
            acceptance_criteria_json='["File exists: nonexistent_xyz.py"]',
        )
        assert result is False
