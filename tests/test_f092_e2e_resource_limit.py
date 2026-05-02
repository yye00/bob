"""Tests for F092: End-to-end test - Resource limit enforcement.

End-to-end integration test that exercises the full resource limit workflow:
Step 1: Create project with max_cost_usd=50
Step 2: Run features that accumulate cost to 55
Step 3: Verify project status becomes resource_limited
Step 4: Verify orchestration loop stops
Step 5: Verify status command shows warning
"""

import json
import sqlite3
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from bob3.cli import main
from bob3.db import (
    create_feature,
    create_project,
    get_project,
    init_database,
    update_feature,
    update_project_cost,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import LoopTermination, OrchestrationLoop


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "bob3.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    ws = tmp_path / "resource-limit-project"
    ws.mkdir()
    return ws


def _init_project(tmp_path, name="resource-limit-test"):
    """Helper: create an initialized project and return (project_path, db_path)."""
    project_path = tmp_path / name
    runner = CliRunner()
    with patch("bob3.cli.start_mcp_server"):
        result = runner.invoke(main, ["init", str(project_path)])
    assert result.exit_code == 0, f"init failed: {result.output}"
    db_path = project_path / "bob3.db"
    return project_path, db_path


def _get_project_id(db_path):
    """Helper: retrieve the first project ID from the database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT id FROM projects LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def _set_project_cost(db_path, total_cost, max_cost, status=None):
    """Helper: set cost and optionally status on the project."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    if status:
        conn.execute(
            "UPDATE projects SET total_cost_usd = ?, max_cost_usd = ?, status = ?",
            (total_cost, max_cost, status),
        )
    else:
        conn.execute(
            "UPDATE projects SET total_cost_usd = ?, max_cost_usd = ?",
            (total_cost, max_cost),
        )
    conn.commit()
    conn.close()


# ============================================================
# Step 1: Create project with max_cost_usd=50
# ============================================================


class TestCreateProjectWithCostLimit:
    """Step 1: Create project with max_cost_usd=50."""

    def test_create_project_with_max_cost_50(self, tmp_db):
        """Project is created with max_cost_usd=50 and total_cost_usd=0."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path="/tmp/resource-limit-test",
                max_cost_usd=50.0,
            )

            assert project.max_cost_usd == 50.0
            assert project.total_cost_usd == 0.0
            assert project.status == "planning"

            # Verify persistence
            fetched = get_project(project.id)
            assert fetched is not None
            assert fetched.max_cost_usd == 50.0
            assert fetched.total_cost_usd == 0.0


# ============================================================
# Step 2: Run features that accumulate cost to 55
# ============================================================


class TestAccumulateCostTo55:
    """Step 2: Run features that accumulate cost to 55."""

    def test_cost_accumulates_to_55_via_update_project_cost(self, tmp_db):
        """Costs accumulate to 55 through incremental updates."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path="/tmp/resource-limit-test",
                max_cost_usd=50.0,
            )

            # Simulate agent runs that accumulate cost
            update_project_cost(project_id=project.id, cost_usd=20.0)
            update_project_cost(project_id=project.id, cost_usd=20.0)
            update_project_cost(project_id=project.id, cost_usd=15.0)

            fetched = get_project(project.id)
            assert fetched.total_cost_usd == 55.0

    @pytest.mark.asyncio
    async def test_features_accumulate_cost_beyond_limit(self, tmp_db, workspace):
        """Multiple features accumulate cost that exceeds the project limit."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path=str(workspace),
                max_cost_usd=50.0,
            )

            # Create 3 features: each will cost ~20 USD (total 60, exceeds 50)
            features = []
            for i in range(3):
                f = create_feature(
                    project_id=project.id,
                    name=f"Costly Feature {i + 1}",
                    description="Feature that costs about $20 to implement",
                    acceptance_criteria=json.dumps([f"Feature {i + 1} works"]),
                    status="ready",
                    priority=10 * (i + 1),
                    risk_category="low",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                features.append(f)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            spawn_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_count
                spawn_count += 1
                mock_result = ExecutionResult(
                    text=f"Feature {spawn_count} implemented",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=10,
                    total_cost_usd=20.0,  # Each feature costs $20
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            # The loop should stop due to budget being exceeded
            assert termination == LoopTermination.BUDGET_EXCEEDED

            # Verify total cost accumulated in the project
            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd > 50.0


# ============================================================
# Step 3: Verify project status becomes resource_limited
# ============================================================


class TestProjectBecomesResourceLimited:
    """Step 3: Verify project status becomes resource_limited."""

    def test_project_status_resource_limited_when_cost_exceeds_max(self, tmp_db):
        """Project status transitions to resource_limited when cost exceeds limit."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path="/tmp/resource-limit-test",
                max_cost_usd=50.0,
            )

            # Accumulate cost in increments that cross the limit
            update_project_cost(project_id=project.id, cost_usd=25.0)
            check1 = get_project(project.id)
            assert check1.status == "planning"  # Still under limit

            update_project_cost(project_id=project.id, cost_usd=20.0)
            check2 = get_project(project.id)
            assert check2.status == "planning"  # 45 < 50, still under

            # Push over the limit: 45 + 10 = 55 > 50
            update_project_cost(project_id=project.id, cost_usd=10.0)
            check3 = get_project(project.id)
            assert check3.total_cost_usd == 55.0
            assert check3.status == "resource_limited"

    def test_single_large_cost_triggers_resource_limited(self, tmp_db):
        """A single cost that exceeds max immediately triggers resource_limited."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path="/tmp/resource-limit-test",
                max_cost_usd=50.0,
            )

            result = update_project_cost(project_id=project.id, cost_usd=55.0)
            assert result.total_cost_usd == 55.0
            assert result.status == "resource_limited"

    def test_resource_limited_persisted_in_database(self, tmp_db):
        """The resource_limited status is persisted in the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path="/tmp/resource-limit-test",
                max_cost_usd=50.0,
            )

            update_project_cost(project_id=project.id, cost_usd=55.0)

            # Re-fetch to verify persistence
            fetched = get_project(project.id)
            assert fetched is not None
            assert fetched.status == "resource_limited"
            assert fetched.total_cost_usd == 55.0


# ============================================================
# Step 4: Verify orchestration loop stops
# ============================================================


class TestOrchestrationLoopStops:
    """Step 4: Verify orchestration loop stops when budget exceeded."""

    @pytest.mark.asyncio
    async def test_loop_stops_with_budget_exceeded(self, tmp_db, workspace):
        """Loop returns BUDGET_EXCEEDED when project cost exceeds max_cost_usd."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path=str(workspace),
                max_cost_usd=50.0,
            )

            # Pre-load cost to just under the limit using update_project_cost
            # (which will also set resource_limited if it crosses the threshold)
            update_project_cost(project_id=project.id, cost_usd=45.0)

            # Create a feature that will push cost over
            feature = create_feature(
                project_id=project.id,
                name="Final Feature",
                description="This will exceed the budget",
                status="ready",
                priority=10,
                risk_category="low",
            )
            update_feature(
                feature.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            # Also create another feature that should NOT be executed
            feature2 = create_feature(
                project_id=project.id,
                name="Should Not Run Feature",
                description="This feature should not be executed due to budget",
                status="ready",
                priority=20,
                risk_category="low",
            )
            update_feature(
                feature2.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            spawn_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_count
                spawn_count += 1
                mock_result = ExecutionResult(
                    text="Feature done",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=10.0,  # 45 + 10 = 55 > 50
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            # Loop should stop with BUDGET_EXCEEDED
            assert termination == LoopTermination.BUDGET_EXCEEDED

            # Only the first feature should have been executed
            assert spawn_count == 1

            # Second feature should still be ready (not executed)
            from bob3.db import get_feature

            f2 = get_feature(feature2.id)
            assert f2.status == "ready"

    @pytest.mark.asyncio
    async def test_loop_stops_with_loop_level_max_cost(self, tmp_db, workspace):
        """Loop also respects the loop-level max_cost parameter."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path=str(workspace),
                max_cost_usd=500.0,  # High project limit
            )

            features = []
            for i in range(3):
                f = create_feature(
                    project_id=project.id,
                    name=f"Feature {i + 1}",
                    status="ready",
                    priority=10 * (i + 1),
                    risk_category="low",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                features.append(f)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
                max_cost=50.0,  # Loop-level budget of $50
            )

            spawn_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_count
                spawn_count += 1
                mock_result = ExecutionResult(
                    text=f"Feature {spawn_count} done",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=20.0,  # Each costs $20
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            # After 3 features ($60 total), loop budget of $50 is exceeded.
            # Bug 1 (2026-04): the canonical accumulator is the DB project
            # total, not loop.total_cost.
            assert termination == LoopTermination.BUDGET_EXCEEDED
            assert get_project(project.id).total_cost_usd >= 50.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_method_detects_project_limit(self, tmp_db):
        """OrchestrationLoop.budget_exceeded() returns True when project cost >= max."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="resource-limit-test",
                workspace_path="/tmp/test",
                max_cost_usd=50.0,
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/test",
            )

            # Under budget
            assert loop.budget_exceeded() is False

            # Push cost over max via update_project_cost
            update_project_cost(project_id=project.id, cost_usd=55.0)

            # ``budget_exceeded`` reads a cached project total to avoid
            # opening a fresh SQLite connection on every loop iteration;
            # the cache is refreshed in production immediately after each
            # cost-mutating write by the loop. This test calls the bare
            # ``db.update_project_cost`` from outside the loop, so we
            # replicate the refresh by hand here.
            loop._refresh_project_cost_cache()

            # Now budget_exceeded should return True
            assert loop.budget_exceeded() is True


# ============================================================
# Step 5: Verify status command shows warning
# ============================================================


class TestStatusCommandShowsWarning:
    """Step 5: Verify status command shows warning when resource limited."""

    def test_status_shows_cost_warning_when_near_limit(self, tmp_path):
        """Status command shows cost warning when approaching budget limit."""
        _, db_path = _init_project(tmp_path)
        _set_project_cost(db_path, total_cost=475.0, max_cost=500.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )

        assert result.exit_code == 0
        assert "$475.00" in result.output
        assert "CRITICAL" in result.output or "near budget limit" in result.output

    def test_status_shows_warning_at_80_percent(self, tmp_path):
        """Status command shows warning when cost is at 80% of budget."""
        _, db_path = _init_project(tmp_path)
        _set_project_cost(db_path, total_cost=42.0, max_cost=50.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )

        assert result.exit_code == 0
        assert "$42.00" in result.output
        assert "WARNING" in result.output or "approaching budget limit" in result.output

    def test_status_shows_resource_limited_status(self, tmp_path):
        """Status command shows resource_limited project status."""
        _, db_path = _init_project(tmp_path)
        _set_project_cost(
            db_path, total_cost=55.0, max_cost=50.0, status="resource_limited"
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )

        assert result.exit_code == 0
        assert "resource_limited" in result.output
        assert "$55.00" in result.output
        # 110% means it should show critical warning
        assert "CRITICAL" in result.output or "near budget limit" in result.output


# ============================================================
# Full end-to-end: All steps combined
# ============================================================


class TestE2EFullResourceLimitEnforcement:
    """Full end-to-end test combining all steps."""

    @pytest.mark.asyncio
    async def test_complete_resource_limit_lifecycle(self, tmp_db, workspace):
        """Complete lifecycle: create project, run features, hit limit, verify everything."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Step 1: Create project with max_cost_usd=50
            project = create_project(
                name="e2e-resource-limit",
                workspace_path=str(workspace),
                max_cost_usd=50.0,
            )
            assert project.max_cost_usd == 50.0
            assert project.total_cost_usd == 0.0

            # Step 2: Create features that will accumulate cost
            features = []
            for i in range(4):
                f = create_feature(
                    project_id=project.id,
                    name=f"Feature {i + 1}",
                    description=f"Feature {i + 1} for resource test",
                    acceptance_criteria=json.dumps([f"Feature {i + 1} implemented"]),
                    status="ready",
                    priority=10 * (i + 1),
                    risk_category="low",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                features.append(f)

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            spawn_count = 0
            feature_costs = [15.0, 15.0, 15.0, 15.0]  # Total $60 > $50

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_count
                cost = feature_costs[spawn_count]
                spawn_count += 1
                mock_result = ExecutionResult(
                    text=f"Feature {spawn_count} done",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=cost,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination = await loop.run()

            # Step 3: Verify cost exceeded 50
            final_project = get_project(project.id)
            assert final_project.total_cost_usd > 50.0

            # Step 4: Verify orchestration loop stopped due to budget
            assert termination == LoopTermination.BUDGET_EXCEEDED

            # At least 3 features ran ($45) before the 4th ($60 total) caused
            # the budget check to trigger
            assert spawn_count >= 3

    def test_update_project_cost_enforces_resource_limited(self, tmp_path):
        """Step 3 via update_project_cost: status becomes resource_limited at 55/50."""
        _, db_path = _init_project(tmp_path)

        with patch("bob3.db.get_database_path", return_value=db_path):
            project_id = _get_project_id(db_path)

            # Set max_cost to 50 first
            from bob3.db import update_project

            update_project(project_id, max_cost_usd=50.0)

            # Accumulate cost to 55 via update_project_cost
            update_project_cost(project_id=project_id, cost_usd=25.0)
            update_project_cost(project_id=project_id, cost_usd=20.0)

            check = get_project(project_id)
            assert check.status == "planning"  # 45 < 50

            update_project_cost(project_id=project_id, cost_usd=10.0)

            final = get_project(project_id)
            assert final.total_cost_usd == 55.0
            assert final.status == "resource_limited"

    def test_status_command_warns_after_resource_limited(self, tmp_path):
        """Step 5: After resource limit hit, status command shows warning."""
        _, db_path = _init_project(tmp_path, name="e2e-status-test")

        # Simulate the end state: resource_limited with cost=55, max=50
        _set_project_cost(
            db_path, total_cost=55.0, max_cost=50.0, status="resource_limited"
        )

        # Step 5: Verify status command shows the warning
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )

        assert result.exit_code == 0
        assert "resource_limited" in result.output
        assert "$55.00" in result.output
        assert "$50.00" in result.output
        # 110% of budget → CRITICAL warning
        assert "CRITICAL" in result.output or "budget limit" in result.output
