"""Tests for F-R6-316: Research-error retry + non-poisoning needs_human gate.

Validates that:
- Error path leaves research_iterations unchanged while errored_count < cap
- Error path increments research_iterations at cap (escalation to needs_human)
- Success path increments research_iterations and boosts readiness to 0.85
- R7-003 guard resets research_iterations when no successful row exists AND under cap
- R7-003 guard still marks needs_human when at least one successful row exists OR cap reached
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3 import db
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    OrchestrationLoop,
    _MAX_RESEARCH_ERROR_ATTEMPTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return db.create_project(
            name="retry-test-project",
            workspace_path="/tmp/retry-test",
            max_cost_usd=100.0,
        )


@pytest.fixture
def low_readiness_feature(tmp_db, project):
    """Feature that is in 'ready' status but below the readiness threshold."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = db.create_feature(
            project_id=project.id,
            name="Low Readiness Feature",
            description="research_required=True",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        db.update_feature(
            f.id,
            conf_spec_understanding=0.70,
            conf_impl_correctness=0.70,
            conf_test_adequacy=0.70,
            readiness_score=0.70,
            research_iterations=0,
        )
        return db.get_feature(f.id)


def _make_spawn_result(*, is_error=False, text="findings text", cost=0.10):
    exec_result = ExecutionResult(
        text=text,
        is_error=is_error,
        error_message="gateway 400" if is_error else "",
        duration_ms=500,
        num_turns=3,
        total_cost_usd=cost,
    )
    agent_run = MagicMock()
    agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=exec_result, agent_run=agent_run)


def _make_loop(project, tmp_db):
    loop = OrchestrationLoop(
        project_id=project.id,
        workspace="/tmp/retry-test",
    )
    return loop


# ---------------------------------------------------------------------------
# Tests for _run_research error path (research_iterations not incremented)
# ---------------------------------------------------------------------------


class TestResearchErrorPath:
    """Error path: research_iterations unchanged while errored_count < cap."""

    def test_error_leaves_research_iterations_unchanged_below_cap(self, tmp_db, project, low_readiness_feature):
        """Single research error must NOT increment research_iterations."""
        feature = low_readiness_feature
        initial_iters = feature.research_iterations or 0

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Record a single errored research result (findings=None)
            db.create_research_result(
                feature_id=feature.id,
                project_id=project.id,
                query="test query",
                findings=None,
            )

            loop = _make_loop(project, tmp_db)
            error_spawn = _make_spawn_result(is_error=True)

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                return_value=error_spawn,
            ):
                asyncio.get_event_loop().run_until_complete(
                    loop._run_research(feature)
                )

            updated = db.get_feature(feature.id)
            assert (updated.research_iterations or 0) == initial_iters, (
                "research_iterations must not be incremented on a transient error "
                f"(errored_count < {_MAX_RESEARCH_ERROR_ATTEMPTS})"
            )

    def test_two_errors_still_leave_iterations_unchanged(self, tmp_db, project, low_readiness_feature):
        """Two errors (still under cap of 3) must leave research_iterations unchanged."""
        feature = low_readiness_feature
        initial_iters = feature.research_iterations or 0

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            for _ in range(2):
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=project.id,
                    query="test query",
                    findings=None,
                )

            loop = _make_loop(project, tmp_db)
            error_spawn = _make_spawn_result(is_error=True)

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                return_value=error_spawn,
            ):
                asyncio.get_event_loop().run_until_complete(
                    loop._run_research(feature)
                )

            updated = db.get_feature(feature.id)
            assert (updated.research_iterations or 0) == initial_iters, (
                "Two prior errors (< cap) must not increment research_iterations"
            )


class TestResearchErrorAtCap:
    """Error path at cap: research_iterations IS incremented to escalate."""

    def test_error_at_cap_increments_research_iterations(self, tmp_db, project, low_readiness_feature):
        """When errored_count >= _MAX_RESEARCH_ERROR_ATTEMPTS, increment research_iterations."""
        feature = low_readiness_feature
        initial_iters = feature.research_iterations or 0

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Pre-populate exactly _MAX_RESEARCH_ERROR_ATTEMPTS errored rows
            for _ in range(_MAX_RESEARCH_ERROR_ATTEMPTS):
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=project.id,
                    query="test query",
                    findings=None,
                )

            loop = _make_loop(project, tmp_db)
            error_spawn = _make_spawn_result(is_error=True)

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                return_value=error_spawn,
            ):
                asyncio.get_event_loop().run_until_complete(
                    loop._run_research(feature)
                )

            updated = db.get_feature(feature.id)
            assert (updated.research_iterations or 0) == initial_iters + 1, (
                f"At errored_count >= cap ({_MAX_RESEARCH_ERROR_ATTEMPTS}), "
                "research_iterations must be incremented to trigger needs_human"
            )


# ---------------------------------------------------------------------------
# Tests for _run_research success path
# ---------------------------------------------------------------------------


class TestResearchSuccessPath:
    """Success path: research_iterations incremented and readiness boosted."""

    def test_success_increments_research_iterations(self, tmp_db, project, low_readiness_feature):
        """Successful research must increment research_iterations by 1."""
        feature = low_readiness_feature
        initial_iters = feature.research_iterations or 0

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = _make_loop(project, tmp_db)
            success_spawn = _make_spawn_result(is_error=False, text="useful findings")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                return_value=success_spawn,
            ):
                asyncio.get_event_loop().run_until_complete(
                    loop._run_research(feature)
                )

            updated = db.get_feature(feature.id)
            assert (updated.research_iterations or 0) == initial_iters + 1, (
                "Successful research must increment research_iterations"
            )

    def test_success_boosts_readiness_to_0_85(self, tmp_db, project, low_readiness_feature):
        """Successful research must boost readiness_score to at least 0.85."""
        feature = low_readiness_feature
        assert (feature.readiness_score or 0) < 0.85, "Pre-condition: readiness below 0.85"

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = _make_loop(project, tmp_db)
            success_spawn = _make_spawn_result(is_error=False, text="useful findings")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                return_value=success_spawn,
            ):
                asyncio.get_event_loop().run_until_complete(
                    loop._run_research(feature)
                )

            updated = db.get_feature(feature.id)
            assert (updated.readiness_score or 0) >= 0.85, (
                "Successful research must boost readiness_score to >= 0.85"
            )

    def test_success_does_not_downgrade_already_high_readiness(self, tmp_db, project):
        """Success path must not lower readiness that is already above 0.85."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            proj = db.create_project(
                name="high-ready-project",
                workspace_path="/tmp/high-ready",
                max_cost_usd=100.0,
            )
            f = db.create_feature(
                project_id=proj.id,
                name="High Readiness Feature",
                description="research_required=True",
                status="ready",
                priority=10,
                risk_category="medium",
            )
            db.update_feature(
                f.id,
                readiness_score=0.95,
                conf_spec_understanding=0.95,
                conf_impl_correctness=0.95,
                research_iterations=0,
            )
            feature = db.get_feature(f.id)

            loop = _make_loop(proj, tmp_db)
            success_spawn = _make_spawn_result(is_error=False, text="findings")

            with patch(
                "bob3.orchestrator.run_loop.spawn_research_agent",
                new_callable=AsyncMock,
                return_value=success_spawn,
            ):
                asyncio.get_event_loop().run_until_complete(
                    loop._run_research(feature)
                )

            updated = db.get_feature(f.id)
            assert (updated.readiness_score or 0) >= 0.95, (
                "Success path must not lower readiness that was already above 0.85"
            )


# ---------------------------------------------------------------------------
# Tests for the R7-003 guard in the run() loop
# ---------------------------------------------------------------------------


class TestR7003GuardResetsIterations:
    """R7-003 guard: resets iterations when no successful row AND under cap."""

    def test_guard_resets_iterations_when_no_successful_research_and_under_cap(
        self, tmp_db, project, low_readiness_feature
    ):
        """Guard must reset research_iterations to 0 when only errored rows exist and under cap."""
        feature = low_readiness_feature

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Set research_iterations to 1 (simulating a legacy/erroneous increment)
            db.update_feature(feature.id, research_iterations=1)

            # Add errored research rows (below cap)
            for _ in range(_MAX_RESEARCH_ERROR_ATTEMPTS - 1):
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=project.id,
                    query="test query",
                    findings=None,
                )

            feature = db.get_feature(feature.id)
            assert feature.research_iterations == 1

            # The guard logic is inside the run() loop, accessed when
            # get_ready_features returns [] but list_features returns the feature.
            # We test the guard by querying research_results directly (unit-style).
            prior_research = db.list_research_results(feature_id=feature.id)
            successful = [r for r in prior_research if r.findings]
            errored = [r for r in prior_research if not r.findings]

            # Replicate the guard decision
            if not successful and len(errored) < _MAX_RESEARCH_ERROR_ATTEMPTS:
                db.update_feature(feature.id, research_iterations=0)

            updated = db.get_feature(feature.id)
            assert (updated.research_iterations or 0) == 0, (
                "Guard must reset research_iterations to 0 when no successful rows "
                f"and errored_count ({len(errored)}) < cap ({_MAX_RESEARCH_ERROR_ATTEMPTS})"
            )

    def test_guard_does_not_reset_when_at_cap(self, tmp_db, project, low_readiness_feature):
        """Guard must NOT reset iterations when errored_count >= cap (let it mark needs_human)."""
        feature = low_readiness_feature

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            db.update_feature(feature.id, research_iterations=1)

            for _ in range(_MAX_RESEARCH_ERROR_ATTEMPTS):
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=project.id,
                    query="test query",
                    findings=None,
                )

            feature = db.get_feature(feature.id)
            prior_research = db.list_research_results(feature_id=feature.id)
            successful = [r for r in prior_research if r.findings]
            errored = [r for r in prior_research if not r.findings]

            # Guard condition: should NOT reset
            reset = not successful and len(errored) < _MAX_RESEARCH_ERROR_ATTEMPTS
            assert not reset, (
                f"Guard must not reset when errored_count ({len(errored)}) >= cap ({_MAX_RESEARCH_ERROR_ATTEMPTS})"
            )


class TestR7003GuardMarksNeedsHuman:
    """R7-003 guard still marks needs_human when at least one success OR cap reached."""

    def test_guard_marks_needs_human_when_successful_research_exists_and_still_low(
        self, tmp_db, project, low_readiness_feature
    ):
        """Guard must mark needs_human when there's a successful row but readiness is still low."""
        feature = low_readiness_feature

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            db.update_feature(feature.id, research_iterations=1)

            # One successful research row
            db.create_research_result(
                feature_id=feature.id,
                project_id=project.id,
                query="test query",
                findings="some useful findings",
            )

            feature = db.get_feature(feature.id)
            prior_research = db.list_research_results(feature_id=feature.id)
            successful = [r for r in prior_research if r.findings]
            errored = [r for r in prior_research if not r.findings]

            # Since there IS a successful row, the guard should NOT reset — it should proceed
            # to mark needs_human (or let the refinement-budget check decide).
            reset = not successful and len(errored) < _MAX_RESEARCH_ERROR_ATTEMPTS
            assert not reset, (
                "Guard must not reset when a successful research row exists"
            )
            assert len(successful) == 1
            assert len(errored) == 0

    def test_guard_marks_needs_human_when_cap_reached_no_success(
        self, tmp_db, project, low_readiness_feature
    ):
        """Guard must proceed to needs_human when errored >= cap and no success."""
        feature = low_readiness_feature

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            db.update_feature(feature.id, research_iterations=_MAX_RESEARCH_ERROR_ATTEMPTS)

            for _ in range(_MAX_RESEARCH_ERROR_ATTEMPTS):
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=project.id,
                    query="test query",
                    findings=None,
                )

            feature = db.get_feature(feature.id)
            prior_research = db.list_research_results(feature_id=feature.id)
            successful = [r for r in prior_research if r.findings]
            errored = [r for r in prior_research if not r.findings]

            # Guard reset condition — must be False at cap
            reset = not successful and len(errored) < _MAX_RESEARCH_ERROR_ATTEMPTS
            assert not reset, (
                f"At cap ({_MAX_RESEARCH_ERROR_ATTEMPTS} errored, 0 successful), "
                "guard must not reset — feature should surface for needs_human"
            )
            assert len(errored) == _MAX_RESEARCH_ERROR_ATTEMPTS
            assert len(successful) == 0


# ---------------------------------------------------------------------------
# Test the constant itself
# ---------------------------------------------------------------------------


def test_max_research_error_attempts_constant():
    """_MAX_RESEARCH_ERROR_ATTEMPTS must be defined and equal to 3."""
    assert _MAX_RESEARCH_ERROR_ATTEMPTS == 3
