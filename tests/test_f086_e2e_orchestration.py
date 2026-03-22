"""Tests for F086: End-to-end test - Create project, add feature, run orchestration.

End-to-end integration test that exercises the full Bob3 workflow:
Step 1: Run bob3 init test-project
Step 2: Manually add a simple feature to database
Step 3: Set feature readiness_score high enough to be ready
Step 4: Run bob3 run
Step 5: Verify sub-agent is spawned
Step 6: Verify feature status updates to completed
Step 7: Verify evidence is created
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from bob3.cli import main
from bob3.db import (
    connect,
    create_feature,
    create_project,
    get_feature,
    get_ready_features,
    init_database,
    list_features,
    query_evidence,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
    handle_execution_result,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "bob3.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory for the project."""
    ws = tmp_path / "test-project"
    ws.mkdir()
    return ws


class TestE2EInitProject:
    """Step 1: Run bob3 init test-project."""

    def test_init_creates_project_and_database(self, tmp_path):
        """bob3 init creates project directory, database, and project record."""
        project_path = tmp_path / "test-project"
        runner = CliRunner()

        with patch("bob3.cli.start_mcp_server"):
            result = runner.invoke(main, ["init", str(project_path)])

        assert result.exit_code == 0
        assert "initialized" in result.output.lower()
        assert project_path.exists()
        assert (project_path / "bob3.db").exists()

    def test_init_inserts_project_record(self, tmp_path):
        """bob3 init inserts a project record into the database."""
        import sqlite3

        project_path = tmp_path / "test-project"
        runner = CliRunner()

        with patch("bob3.cli.start_mcp_server"):
            result = runner.invoke(main, ["init", str(project_path)])

        assert result.exit_code == 0

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            row = conn.execute("SELECT name, status FROM projects LIMIT 1").fetchone()
            assert row is not None
            assert row[0] == "test-project"
            assert row[1] == "planning"
        finally:
            conn.close()


class TestE2EAddFeature:
    """Step 2: Manually add a simple feature to database."""

    def test_create_feature_in_database(self, tmp_db):
        """A feature can be created programmatically and persisted."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path="/tmp/test-project",
            )
            feature = create_feature(
                project_id=project.id,
                name="Hello World Feature",
                description="Print hello world",
                acceptance_criteria=json.dumps(["Output contains 'hello world'"]),
                status="pending",
                priority=10,
                risk_category="low",
            )

            assert feature.id is not None
            assert feature.project_id == project.id
            assert feature.name == "Hello World Feature"
            assert feature.status == "pending"

            # Verify it persisted to DB
            retrieved = get_feature(feature.id)
            assert retrieved is not None
            assert retrieved.name == "Hello World Feature"


class TestE2ESetReadiness:
    """Step 3: Set feature readiness_score high enough to be ready."""

    def test_set_readiness_and_status_to_ready(self, tmp_db):
        """Feature becomes ready when readiness_score exceeds threshold."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path="/tmp/test-project",
            )
            feature = create_feature(
                project_id=project.id,
                name="Ready Feature",
                description="A feature that is ready",
                status="ready",
                priority=10,
                risk_category="low",  # threshold = 0.70
            )
            update_feature(
                feature.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            # Verify readiness is above the threshold
            updated = get_feature(feature.id)
            assert updated.readiness_score >= 0.70
            assert updated.status == "ready"

            # Verify it appears in ready features list
            ready = get_ready_features(project.id)
            assert len(ready) == 1
            assert ready[0].id == feature.id


class TestE2ERunOrchestration:
    """Step 4-7: Run bob3 run and verify full orchestration flow."""

    @pytest.mark.asyncio
    async def test_full_orchestration_flow(self, tmp_db, workspace):
        """Full end-to-end: init -> add feature -> set ready -> run -> verify."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Step 1: Create project
            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
            )

            # Step 2: Add a feature
            feature = create_feature(
                project_id=project.id,
                name="E2E Test Feature",
                description="A simple feature for end-to-end testing",
                acceptance_criteria=json.dumps(["Feature is implemented"]),
                status="ready",
                priority=10,
                risk_category="low",
            )

            # Step 3: Set readiness high enough
            update_feature(
                feature.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            # Verify feature is ready
            ready = get_ready_features(project.id)
            assert len(ready) == 1

            # Step 4: Run orchestration loop with mocked sub-agent
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            agent_run_id = str(uuid.uuid4())
            spawn_called = False

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_called
                spawn_called = True

                # Step 5: Verify sub-agent is spawned (this function being
                # called proves it)
                assert kwargs.get("purpose") == "implement_feature"
                assert kwargs.get("target_type") == "feature"
                assert kwargs.get("target_id") == feature.id

                mock_result = ExecutionResult(
                    text="Feature implemented successfully. All tests pass.",
                    is_error=False,
                    duration_ms=5000,
                    num_turns=10,
                    total_cost_usd=1.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = agent_run_id
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

            # Step 5: Verify sub-agent was spawned
            assert spawn_called, "Sub-agent should have been spawned"

            # Step 6: Verify feature status updates to completed
            completed_feature = get_feature(feature.id)
            assert completed_feature.status == "completed"

            # Verify the loop terminated with ALL_COMPLETED
            assert termination == LoopTermination.ALL_COMPLETED

            # Step 7: Verify evidence is created
            evidence = query_evidence(feature_id=feature.id)
            assert len(evidence) >= 1
            # Find the execution_output evidence (F113 may add verification_checklist after it)
            exec_evidence = [e for e in evidence if e.type == "execution_output"]
            assert len(exec_evidence) >= 1
            latest_evidence = exec_evidence[-1]
            assert latest_evidence.type == "execution_output"
            assert latest_evidence.feature_id == feature.id
            assert latest_evidence.project_id == project.id

            # Verify evidence content has expected structure
            content = json.loads(latest_evidence.content)
            assert content["status"] == "completed"
            assert "output_text" in content
            assert content["cost_usd"] == 1.50

    @pytest.mark.asyncio
    async def test_failed_feature_creates_error_evidence(self, tmp_db, workspace):
        """When a sub-agent fails, error evidence is created and status reflects failure."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
            )
            feature = create_feature(
                project_id=project.id,
                name="Failing Feature",
                description="A feature that will fail",
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

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            async def mock_spawn_failure(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="Build failed",
                    is_error=True,
                    error_message="Tests did not pass",
                    duration_ms=3000,
                    num_turns=5,
                    total_cost_usd=0.75,
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
                side_effect=mock_spawn_failure,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ):
                termination = await loop.run()

            # F071: First failure resets to 'ready' for retry, subsequent failures
            # eventually lead to 'needs_human'. After exhausting retries the loop
            # should terminate as ALL_BLOCKED (the feature is needs_human).
            final_feature = get_feature(feature.id)
            assert final_feature.status in ("ready", "failed", "needs_human")

            # Evidence should exist (at least one error evidence per attempt)
            evidence = query_evidence(feature_id=feature.id)
            assert len(evidence) >= 1
            # At least one error evidence
            error_evidence = [e for e in evidence if e.type == "execution_error"]
            assert len(error_evidence) >= 1

    @pytest.mark.asyncio
    async def test_multiple_features_processed_in_sequence(self, tmp_db, workspace):
        """Multiple ready features are processed one after another."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
            )

            features = []
            for i in range(3):
                f = create_feature(
                    project_id=project.id,
                    name=f"Feature {i + 1}",
                    description=f"Test feature {i + 1}",
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
                    text=f"Feature {spawn_count} done",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=0.50,
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

            # All 3 features should be processed
            assert spawn_count == 3
            assert termination == LoopTermination.ALL_COMPLETED

            # All features should be completed
            for f in features:
                updated = get_feature(f.id)
                assert updated.status == "completed"

            # Each feature should have evidence
            for f in features:
                evidence = query_evidence(feature_id=f.id)
                assert len(evidence) >= 1

            # Total cost should be accumulated
            assert loop.total_cost == pytest.approx(1.50)


class TestE2ECLIIntegration:
    """Test the full flow via CLI commands."""

    def test_init_then_run_via_cli(self, tmp_path):
        """CLI init + run --all works end-to-end."""
        project_path = tmp_path / "cli-test-project"
        runner = CliRunner()

        # Step 1: Init project via CLI
        with patch("bob3.cli.start_mcp_server"):
            result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0

        # Step 2-3: Add a ready feature directly to the database
        import sqlite3

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            project_row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
            project_id = project_row[0]
            feature_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO features
                   (id, project_id, name, description, status, priority,
                    risk_category, conf_spec_understanding, conf_impl_correctness,
                    conf_test_adequacy, readiness_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (feature_id, project_id, "CLI E2E Feature",
                 "Test feature for CLI integration", "ready", 10,
                 "low", 0.9, 0.9, 0.9, 0.9),
            )
            conn.commit()
        finally:
            conn.close()

        # Step 4: Run via CLI (mock the orchestration loop)
        with patch("bob3.db.get_database_path", return_value=db_path):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=LoopTermination.ALL_COMPLETED,
                ) as mock_loop:
                    result = runner.invoke(main, ["run", "--all"])
                    assert result.exit_code == 0
                    mock_loop.assert_called_once()
                    # Verify the project_id argument is a non-empty string
                    call_args = mock_loop.call_args
                    called_project_id = call_args[0][0]
                    assert isinstance(called_project_id, str) and len(called_project_id) > 0
                    assert call_args[1].get("max_cost") is None
                    assert call_args[1].get("fresh") is False
                    assert "completed" in result.output.lower()

    def test_init_run_with_budget(self, tmp_path):
        """CLI init + run --all --max-cost respects budget parameter."""
        project_path = tmp_path / "budget-test-project"
        runner = CliRunner()

        with patch("bob3.cli.start_mcp_server"):
            result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0

        db_path = project_path / "bob3.db"

        with patch("bob3.db.get_database_path", return_value=db_path):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=LoopTermination.BUDGET_EXCEEDED,
                ) as mock_loop:
                    result = runner.invoke(
                        main, ["run", "--all", "--max-cost", "25.0"]
                    )
                    assert result.exit_code == 0
                    call_kwargs = mock_loop.call_args
                    assert call_kwargs[1].get("max_cost") == 25.0 or (
                        len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 25.0
                    )


class TestE2EHandleExecutionResult:
    """Test handle_execution_result creates evidence and updates status."""

    def test_successful_execution_creates_output_evidence(self, tmp_db, workspace):
        """Successful execution creates execution_output evidence artifact."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
            )
            feature = create_feature(
                project_id=project.id,
                name="Test Feature",
                status="executing",
                priority=10,
            )

            mock_result = ExecutionResult(
                text="All tests pass. Feature implemented.",
                is_error=False,
                duration_ms=5000,
                num_turns=10,
                total_cost_usd=1.00,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=mock_result,
                agent_run=mock_agent_run,
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            assert outcome["success"] is True
            assert outcome["evidence_id"] is not None

            # Check feature status
            updated_feature = get_feature(feature.id)
            assert updated_feature.status == "completed"

            # Check evidence
            evidence = query_evidence(feature_id=feature.id)
            assert len(evidence) == 1
            assert evidence[0].type == "execution_output"

            content = json.loads(evidence[0].content)
            assert content["status"] == "completed"
            assert content["cost_usd"] == 1.00

    def test_failed_execution_creates_error_evidence(self, tmp_db, workspace):
        """Failed execution creates execution_error evidence artifact."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
            )
            feature = create_feature(
                project_id=project.id,
                name="Failing Feature",
                status="executing",
                priority=10,
            )

            mock_result = ExecutionResult(
                text="Error output",
                is_error=True,
                error_message="Compilation failed",
                duration_ms=2000,
                num_turns=3,
                total_cost_usd=0.50,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=mock_result,
                agent_run=mock_agent_run,
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            assert outcome["success"] is False
            assert outcome["evidence_id"] is not None

            # Check feature status
            updated_feature = get_feature(feature.id)
            assert updated_feature.status == "failed"

            # Check evidence
            evidence = query_evidence(feature_id=feature.id)
            assert len(evidence) == 1
            assert evidence[0].type == "execution_error"

            content = json.loads(evidence[0].content)
            assert content["status"] == "failed"
            assert content["error_message"] == "Compilation failed"


class TestE2EReadinessGating:
    """Test that features below readiness threshold are not picked up."""

    def test_low_readiness_feature_not_selected(self, tmp_db):
        """Feature with low readiness is not selected for execution."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path="/tmp/test-project",
            )
            feature = create_feature(
                project_id=project.id,
                name="Not Ready Feature",
                description="Low readiness score",
                status="ready",
                priority=10,
                risk_category="medium",  # threshold = 0.80
            )
            update_feature(
                feature.id,
                readiness_score=0.50,  # Below medium threshold
            )

            ready = get_ready_features(project.id)
            assert len(ready) == 0

    @pytest.mark.asyncio
    async def test_loop_terminates_blocked_with_unready_features(self, tmp_db, workspace):
        """Orchestration loop terminates as ALL_BLOCKED when features aren't ready."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
            )
            feature = create_feature(
                project_id=project.id,
                name="Pending Feature",
                description="Not yet ready",
                status="pending",
                priority=10,
                risk_category="medium",
            )
            update_feature(
                feature.id,
                readiness_score=0.50,
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )
            termination = await loop.run()
            assert termination == LoopTermination.ALL_BLOCKED


class TestE2ECostTracking:
    """Test that costs are properly tracked throughout the orchestration."""

    @pytest.mark.asyncio
    async def test_project_cost_updated_after_execution(self, tmp_db, workspace):
        """Project total_cost_usd is updated after feature execution."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import get_project

            project = create_project(
                name="test-project",
                workspace_path=str(workspace),
                total_cost_usd=0.0,
            )
            feature = create_feature(
                project_id=project.id,
                name="Cost Tracking Feature",
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

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
            )

            async def mock_spawn(*args, **kwargs):
                mock_result = ExecutionResult(
                    text="done",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=2.50,
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
                await loop.run()

            # Loop-level cost tracking
            assert loop.total_cost == pytest.approx(2.50)

            # Project-level cost should be updated
            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(2.50)
