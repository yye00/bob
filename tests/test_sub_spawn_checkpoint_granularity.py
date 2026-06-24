"""Tests for sub-spawn checkpoint granularity.

Verifies that compile-and-verify cycles emit fine-grained checkpoints
after each compiler invocation and after each test class, not just at
feature completion.
"""

from __future__ import annotations

import json

import pytest

from bob import db
from bob.sub_spawn_checkpoint_granularity import (
    CompilerResult,
    GranularVerifyRunner,
    TestClassResult,
    VerifyCycleState,
    checkpoint_after_compiler,
    checkpoint_after_test_class,
    checkpoint_after_verify_cycle,
    find_latest_cycle_checkpoint,
    load_cycle_state_from_checkpoint,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Use a fresh temporary database for every test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    return db.create_project(name="GCG Test Project", workspace_path="/tmp/gcg")


@pytest.fixture()
def feature(project):
    return db.create_feature(
        project_id=project.id,
        name="GCG Feature",
        description="Granular checkpoint test feature",
        status="executing",
    )


@pytest.fixture()
def cycle_state(feature):
    return VerifyCycleState(
        feature_id=feature.id,
        project_id=feature.project_id,
    )


# ---------------------------------------------------------------------------
# CompilerResult / TestClassResult data classes
# ---------------------------------------------------------------------------


class TestCompilerResult:
    def test_success_field(self):
        r = CompilerResult(success=True, returncode=0)
        assert r.success is True
        assert r.returncode == 0

    def test_failure_captures_stderr(self):
        r = CompilerResult(success=False, returncode=1, stderr="SyntaxError")
        assert r.success is False
        assert "SyntaxError" in r.stderr

    def test_files_checked_default_empty(self):
        r = CompilerResult(success=True, returncode=0)
        assert r.files_checked == []


class TestTestClassResult:
    def test_success_property_all_zero_failures(self):
        r = TestClassResult(class_name="TestFoo", passed=3, failed=0, errors=0)
        assert r.success is True

    def test_success_false_when_failures(self):
        r = TestClassResult(class_name="TestFoo", passed=2, failed=1, errors=0)
        assert r.success is False

    def test_success_false_when_errors(self):
        r = TestClassResult(class_name="TestFoo", passed=2, failed=0, errors=1)
        assert r.success is False


# ---------------------------------------------------------------------------
# VerifyCycleState serialisation
# ---------------------------------------------------------------------------


class TestVerifyCycleState:
    def test_round_trip(self, feature):
        state = VerifyCycleState(
            feature_id=feature.id,
            project_id=feature.project_id,
            compiler_steps_done=["mypy", "ruff"],
            test_classes_done=["TestFoo"],
            total_cost_usd=1.5,
            total_duration_ms=4000,
        )
        data = state.to_dict()
        restored = VerifyCycleState.from_dict(data)
        assert restored.feature_id == state.feature_id
        assert restored.project_id == state.project_id
        assert restored.compiler_steps_done == ["mypy", "ruff"]
        assert restored.test_classes_done == ["TestFoo"]
        assert restored.total_cost_usd == 1.5
        assert restored.total_duration_ms == 4000

    def test_from_dict_defaults(self, feature):
        data = {"feature_id": feature.id, "project_id": feature.project_id}
        state = VerifyCycleState.from_dict(data)
        assert state.compiler_steps_done == []
        assert state.test_classes_done == []
        assert state.total_cost_usd == 0.0
        assert state.total_duration_ms == 0


# ---------------------------------------------------------------------------
# checkpoint_after_compiler
# ---------------------------------------------------------------------------


class TestCheckpointAfterCompiler:
    def test_creates_checkpoint_with_correct_type(self, cycle_state):
        result = CompilerResult(success=True, returncode=0)
        cp_id = checkpoint_after_compiler(
            state=cycle_state,
            result=result,
            step_name="mypy",
        )
        cp = db.get_checkpoint(cp_id)
        assert cp is not None
        assert cp.checkpoint_type == "compiler_invocation"

    def test_step_name_appended_to_state(self, cycle_state):
        result = CompilerResult(success=True, returncode=0)
        checkpoint_after_compiler(state=cycle_state, result=result, step_name="ruff")
        assert "ruff" in cycle_state.compiler_steps_done

    def test_snapshot_contains_step_info(self, cycle_state):
        result = CompilerResult(
            success=False, returncode=1, files_checked=["src/foo.py"]
        )
        cp_id = checkpoint_after_compiler(
            state=cycle_state, result=result, step_name="mypy"
        )
        cp = db.get_checkpoint(cp_id)
        snapshot = json.loads(cp.state_snapshot)
        assert snapshot["last_compiler_step"] == "mypy"
        assert snapshot["last_compiler_success"] is False
        assert snapshot["last_compiler_returncode"] == 1
        assert "src/foo.py" in snapshot["last_compiler_files_checked"]

    def test_state_last_checkpoint_id_updated(self, cycle_state):
        result = CompilerResult(success=True, returncode=0)
        cp_id = checkpoint_after_compiler(
            state=cycle_state, result=result, step_name="mypy"
        )
        assert cycle_state.last_checkpoint_id == cp_id

    def test_multiple_steps_accumulate_in_state(self, cycle_state):
        for step in ("mypy", "ruff", "pytest-collect"):
            checkpoint_after_compiler(
                state=cycle_state,
                result=CompilerResult(success=True, returncode=0),
                step_name=step,
            )
        assert cycle_state.compiler_steps_done == ["mypy", "ruff", "pytest-collect"]


# ---------------------------------------------------------------------------
# checkpoint_after_test_class
# ---------------------------------------------------------------------------


class TestCheckpointAfterTestClass:
    def test_creates_checkpoint_with_correct_type(self, cycle_state):
        result = TestClassResult(class_name="TestFoo", passed=3, failed=0, errors=0)
        cp_id = checkpoint_after_test_class(state=cycle_state, result=result)
        cp = db.get_checkpoint(cp_id)
        assert cp is not None
        assert cp.checkpoint_type == "test_class"

    def test_class_name_appended_to_state(self, cycle_state):
        result = TestClassResult(class_name="TestBar", passed=1, failed=0, errors=0)
        checkpoint_after_test_class(state=cycle_state, result=result)
        assert "TestBar" in cycle_state.test_classes_done

    def test_snapshot_contains_class_info(self, cycle_state):
        result = TestClassResult(
            class_name="TestBaz", passed=2, failed=1, errors=0,
            failure_messages=["AssertionError: expected 1"]
        )
        cp_id = checkpoint_after_test_class(state=cycle_state, result=result)
        cp = db.get_checkpoint(cp_id)
        snapshot = json.loads(cp.state_snapshot)
        assert snapshot["last_test_class"] == "TestBaz"
        assert snapshot["last_test_class_passed"] == 2
        assert snapshot["last_test_class_failed"] == 1
        assert snapshot["last_test_class_success"] is False

    def test_state_last_checkpoint_id_updated(self, cycle_state):
        result = TestClassResult(class_name="TestFoo", passed=1, failed=0, errors=0)
        cp_id = checkpoint_after_test_class(state=cycle_state, result=result)
        assert cycle_state.last_checkpoint_id == cp_id


# ---------------------------------------------------------------------------
# checkpoint_after_verify_cycle
# ---------------------------------------------------------------------------


class TestCheckpointAfterVerifyCycle:
    def test_creates_verify_cycle_checkpoint(self, cycle_state):
        cp_id = checkpoint_after_verify_cycle(state=cycle_state, all_passed=True)
        cp = db.get_checkpoint(cp_id)
        assert cp is not None
        assert cp.checkpoint_type == "verify_cycle"

    def test_snapshot_reflects_all_passed(self, cycle_state):
        cp_id = checkpoint_after_verify_cycle(state=cycle_state, all_passed=True)
        cp = db.get_checkpoint(cp_id)
        snapshot = json.loads(cp.state_snapshot)
        assert snapshot["all_passed"] is True
        assert snapshot["cycle_complete"] is True

    def test_snapshot_reflects_failure(self, cycle_state):
        cp_id = checkpoint_after_verify_cycle(state=cycle_state, all_passed=False)
        cp = db.get_checkpoint(cp_id)
        snapshot = json.loads(cp.state_snapshot)
        assert snapshot["all_passed"] is False


# ---------------------------------------------------------------------------
# load_cycle_state_from_checkpoint
# ---------------------------------------------------------------------------


class TestLoadCycleStateFromCheckpoint:
    def test_restores_state(self, cycle_state):
        cycle_state.compiler_steps_done = ["mypy"]
        cycle_state.test_classes_done = ["TestFoo"]
        cycle_state.total_cost_usd = 2.5
        cp_id = checkpoint_after_verify_cycle(state=cycle_state, all_passed=True)

        restored = load_cycle_state_from_checkpoint(cp_id)
        assert restored.feature_id == cycle_state.feature_id
        assert restored.project_id == cycle_state.project_id
        assert restored.compiler_steps_done == ["mypy"]
        assert restored.test_classes_done == ["TestFoo"]
        assert restored.total_cost_usd == 2.5

    def test_raises_on_missing_checkpoint(self):
        with pytest.raises(ValueError, match="not found"):
            load_cycle_state_from_checkpoint("nonexistent-id")

    def test_last_checkpoint_id_set_on_restore(self, cycle_state):
        cp_id = checkpoint_after_verify_cycle(state=cycle_state, all_passed=True)
        restored = load_cycle_state_from_checkpoint(cp_id)
        assert restored.last_checkpoint_id == cp_id


# ---------------------------------------------------------------------------
# find_latest_cycle_checkpoint
# ---------------------------------------------------------------------------


class TestFindLatestCycleCheckpoint:
    def test_returns_none_when_no_checkpoints(self, feature):
        result = find_latest_cycle_checkpoint(
            feature_id=feature.id, project_id=feature.project_id
        )
        assert result is None

    def test_returns_latest_resumable(self, cycle_state, feature):
        checkpoint_after_compiler(
            state=cycle_state,
            result=CompilerResult(success=True, returncode=0),
            step_name="mypy",
        )
        cp2_id = checkpoint_after_test_class(
            state=cycle_state,
            result=TestClassResult(class_name="TestFoo", passed=1, failed=0, errors=0),
        )
        found = find_latest_cycle_checkpoint(
            feature_id=feature.id, project_id=feature.project_id
        )
        assert found == cp2_id

    def test_filters_by_checkpoint_type(self, cycle_state, feature):
        checkpoint_after_compiler(
            state=cycle_state,
            result=CompilerResult(success=True, returncode=0),
            step_name="mypy",
        )
        checkpoint_after_test_class(
            state=cycle_state,
            result=TestClassResult(class_name="TestFoo", passed=1, failed=0, errors=0),
        )
        found = find_latest_cycle_checkpoint(
            feature_id=feature.id,
            project_id=feature.project_id,
            checkpoint_type="compiler_invocation",
        )
        cp = db.get_checkpoint(found)
        assert cp.checkpoint_type == "compiler_invocation"

    def test_excludes_already_resumed_checkpoints(self, cycle_state, feature):
        cp_id = checkpoint_after_compiler(
            state=cycle_state,
            result=CompilerResult(success=True, returncode=0),
            step_name="mypy",
        )
        # mark as resumed
        db.resume_from_checkpoint(cp_id)

        found = find_latest_cycle_checkpoint(
            feature_id=feature.id, project_id=feature.project_id
        )
        assert found is None


# ---------------------------------------------------------------------------
# GranularVerifyRunner
# ---------------------------------------------------------------------------


class TestGranularVerifyRunner:
    def test_compiler_step_creates_checkpoint(self, cycle_state, feature):
        runner = GranularVerifyRunner(state=cycle_state)
        runner.run_compiler_step("mypy", lambda: CompilerResult(success=True, returncode=0))

        checkpoints = db.list_checkpoints(feature_id=feature.id)
        assert any(cp.checkpoint_type == "compiler_invocation" for cp in checkpoints)

    def test_test_class_step_creates_checkpoint(self, cycle_state, feature):
        runner = GranularVerifyRunner(state=cycle_state)
        runner.run_test_class(
            "TestFoo",
            lambda: TestClassResult(class_name="TestFoo", passed=2, failed=0, errors=0),
        )

        checkpoints = db.list_checkpoints(feature_id=feature.id)
        assert any(cp.checkpoint_type == "test_class" for cp in checkpoints)

    def test_finalize_creates_verify_cycle_checkpoint(self, cycle_state, feature):
        runner = GranularVerifyRunner(state=cycle_state)
        runner.run_compiler_step("mypy", lambda: CompilerResult(success=True, returncode=0))
        runner.finalize()

        checkpoints = db.list_checkpoints(feature_id=feature.id)
        assert any(cp.checkpoint_type == "verify_cycle" for cp in checkpoints)

    def test_all_passed_true_when_all_succeed(self, cycle_state):
        runner = GranularVerifyRunner(state=cycle_state)
        runner.run_compiler_step("mypy", lambda: CompilerResult(success=True, returncode=0))
        runner.run_test_class(
            "TestFoo",
            lambda: TestClassResult(class_name="TestFoo", passed=3, failed=0, errors=0),
        )
        assert runner.all_passed is True

    def test_all_passed_false_when_compiler_fails(self, cycle_state):
        runner = GranularVerifyRunner(state=cycle_state)
        runner.run_compiler_step("mypy", lambda: CompilerResult(success=False, returncode=1))
        assert runner.all_passed is False

    def test_all_passed_false_when_test_fails(self, cycle_state):
        runner = GranularVerifyRunner(state=cycle_state)
        runner.run_compiler_step("mypy", lambda: CompilerResult(success=True, returncode=0))
        runner.run_test_class(
            "TestFoo",
            lambda: TestClassResult(class_name="TestFoo", passed=0, failed=2, errors=0),
        )
        assert runner.all_passed is False

    def test_already_done_compiler_step_skipped(self, cycle_state):
        """A step already in compiler_steps_done is not re-executed."""
        cycle_state.compiler_steps_done = ["mypy"]
        runner = GranularVerifyRunner(state=cycle_state)

        calls = []
        def compiler_fn():
            calls.append(True)
            return CompilerResult(success=True, returncode=0)

        result = runner.run_compiler_step("mypy", compiler_fn)
        assert calls == []  # not called
        assert result.success is True

    def test_already_done_test_class_skipped(self, cycle_state):
        """A test class already in test_classes_done is not re-executed."""
        cycle_state.test_classes_done = ["TestFoo"]
        runner = GranularVerifyRunner(state=cycle_state)

        calls = []
        def test_fn():
            calls.append(True)
            return TestClassResult(class_name="TestFoo", passed=1, failed=0, errors=0)

        result = runner.run_test_class("TestFoo", test_fn)
        assert calls == []  # not called
        assert result.success is True

    def test_multiple_steps_all_checkpointed(self, cycle_state, feature):
        runner = GranularVerifyRunner(state=cycle_state)
        for step in ("mypy", "ruff"):
            runner.run_compiler_step(step, lambda: CompilerResult(success=True, returncode=0))
        for cls in ("TestA", "TestB"):
            c = cls
            runner.run_test_class(
                c, lambda c=c: TestClassResult(class_name=c, passed=1, failed=0, errors=0)
            )
        runner.finalize()

        checkpoints = db.list_checkpoints(feature_id=feature.id)
        types = [cp.checkpoint_type for cp in checkpoints]
        assert types.count("compiler_invocation") == 2
        assert types.count("test_class") == 2
        assert types.count("verify_cycle") == 1

    def test_resume_skips_completed_work(self, cycle_state, feature):
        """Simulate a mid-run interruption and resume from checkpoint."""
        # First partial run: one compiler step done, then interrupted
        runner1 = GranularVerifyRunner(state=cycle_state)
        runner1.run_compiler_step("mypy", lambda: CompilerResult(success=True, returncode=0))
        saved_cp_id = cycle_state.last_checkpoint_id

        # Restore state from checkpoint and continue
        restored_state = load_cycle_state_from_checkpoint(saved_cp_id)
        runner2 = GranularVerifyRunner(state=restored_state)

        mypy_calls = []
        ruff_calls = []
        runner2.run_compiler_step("mypy", lambda: (mypy_calls.append(1), CompilerResult(success=True, returncode=0))[1])
        runner2.run_compiler_step("ruff", lambda: (ruff_calls.append(1), CompilerResult(success=True, returncode=0))[1])
        runner2.finalize()

        # mypy was already done, so it must NOT have been called again
        assert mypy_calls == []
        # ruff was not done, so it MUST have been called
        assert ruff_calls == [1]

        checkpoints = db.list_checkpoints(feature_id=feature.id)
        assert any(cp.checkpoint_type == "verify_cycle" for cp in checkpoints)
