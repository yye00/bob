"""Tests for F070: Handle feature execution results in orchestration loop.

Tests that the orchestration loop properly:
- Parses sub-agent results (success/failure)
- Updates feature status (completed/failed)
- Creates evidence artifacts from results
- Updates cost tracking
- Runs feature to completion with status and evidence updated
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    create_feature,
    create_project,
    get_feature,
    get_project,
    init_database,
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
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="test-project",
            workspace_path="/tmp/test-project",
            max_cost_usd=100.0,
        )


@pytest.fixture
def feature(tmp_db, project):
    """Create a single ready feature."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        f = create_feature(
            project_id=project.id,
            name="Test Feature",
            description="A test feature for result handling",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        return get_feature(f.id)


# ============================================================
# Step 1: Parse sub-agent results (success/failure)
# ============================================================


class TestParseSubAgentResults:
    """Test that handle_execution_result correctly parses success/failure."""

    def test_parse_successful_result(self, tmp_db, project, feature):
        """Step 1: A non-error result is parsed as success."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="Feature implemented successfully.\nAll tests pass.",
                is_error=False,
                duration_ms=5000,
                num_turns=10,
                total_cost_usd=1.50,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            assert outcome["success"] is True
            assert outcome["cost_usd"] == 1.50
            assert outcome["duration_ms"] == 5000

    def test_parse_failed_result(self, tmp_db, project, feature):
        """Step 1: An error result is parsed as failure."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="",
                is_error=True,
                error_message="Build failed: syntax error in main.py",
                duration_ms=2000,
                num_turns=3,
                total_cost_usd=0.30,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            assert outcome["success"] is False
            assert outcome["error_message"] == "Build failed: syntax error in main.py"

    def test_parse_result_with_none_cost(self, tmp_db, project, feature):
        """Step 1: A result with None cost is handled gracefully."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="Done",
                is_error=False,
                duration_ms=1000,
                num_turns=2,
                total_cost_usd=None,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            assert outcome["success"] is True
            assert outcome["cost_usd"] is None


# ============================================================
# Step 2: Update feature status (completed/failed)
# ============================================================


class TestUpdateFeatureStatus:
    """Test that handle_execution_result updates feature status."""

    def test_success_sets_completed(self, tmp_db, project, feature):
        """Step 2: Successful result sets feature status to 'completed'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="All good", is_error=False, total_cost_usd=1.0
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            updated = get_feature(feature.id)
            assert updated.status == "completed"

    def test_failure_sets_failed(self, tmp_db, project, feature):
        """Step 2: Failed result sets feature status to 'failed'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="", is_error=True, error_message="crash", total_cost_usd=0.5
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            updated = get_feature(feature.id)
            assert updated.status == "failed"

    def test_interrupted_sets_interrupted(self, tmp_db, project, feature):
        """Step 2: When shutdown_requested, error sets 'interrupted' status."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="", is_error=True, error_message="shutdown", total_cost_usd=0.5
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
                shutdown_requested=True,
            )

            updated = get_feature(feature.id)
            assert updated.status == "interrupted"


# ============================================================
# Step 3: Create evidence artifacts from results
# ============================================================


class TestCreateEvidenceArtifacts:
    """Test that handle_execution_result creates evidence artifacts."""

    def test_success_creates_execution_output_evidence(self, tmp_db, project, feature):
        """Step 3: Successful execution creates an 'execution_output' evidence artifact."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="Feature implemented.\nTests pass.\n5 files changed.",
                is_error=False,
                duration_ms=5000,
                num_turns=8,
                total_cost_usd=1.50,
                tool_uses=["Read", "Edit", "Bash"],
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            # Check evidence was created
            evidence_list = query_evidence(
                project_id=project.id, feature_id=feature.id
            )
            assert len(evidence_list) >= 1

            # Find the execution_output evidence
            exec_evidence = [e for e in evidence_list if e.type == "execution_output"]
            assert len(exec_evidence) == 1
            import json
            content = json.loads(exec_evidence[0].content)
            assert content["status"] == "completed"
            assert content["duration_ms"] == 5000
            assert content["num_turns"] == 8
            assert "Feature implemented" in content["output_text"]

    def test_failure_creates_execution_error_evidence(self, tmp_db, project, feature):
        """Step 3: Failed execution creates an 'execution_error' evidence artifact."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="Attempted implementation but failed",
                is_error=True,
                error_message="Tests failed: 3 failures",
                duration_ms=3000,
                num_turns=5,
                total_cost_usd=0.80,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            evidence_list = query_evidence(
                project_id=project.id, feature_id=feature.id
            )
            error_evidence = [e for e in evidence_list if e.type == "execution_error"]
            assert len(error_evidence) == 1
            import json
            content = json.loads(error_evidence[0].content)
            assert content["status"] == "failed"
            assert content["error_message"] == "Tests failed: 3 failures"

    def test_evidence_includes_agent_run_id(self, tmp_db, project, feature):
        """Step 3: Evidence content includes the agent_run_id for traceability."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="Done", is_error=False, total_cost_usd=1.0
            )
            run_id = str(uuid.uuid4())
            agent_run = MagicMock()
            agent_run.id = run_id
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            evidence_list = query_evidence(
                project_id=project.id, feature_id=feature.id
            )
            assert len(evidence_list) >= 1
            import json
            content = json.loads(evidence_list[0].content)
            assert content["agent_run_id"] == run_id

    def test_evidence_references_feature_id(self, tmp_db, project, feature):
        """Step 3: Evidence artifacts reference the feature_id."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=0.5
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            evidence_list = query_evidence(
                project_id=project.id, feature_id=feature.id
            )
            assert len(evidence_list) >= 1
            assert all(e.feature_id == feature.id for e in evidence_list)


# ============================================================
# Step 4: Update cost tracking
# ============================================================


class TestUpdateCostTracking:
    """Test that handle_execution_result updates cost tracking."""

    def test_project_cost_updated_on_success(self, tmp_db, project, feature):
        """Step 4: Project total_cost_usd is updated after successful execution."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=2.50
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(2.50)

    def test_project_cost_updated_on_failure(self, tmp_db, project, feature):
        """Step 4: Project cost is still updated even on failure."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="", is_error=True, error_message="fail", total_cost_usd=0.75
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(0.75)

    def test_cost_not_updated_when_none(self, tmp_db, project, feature):
        """Step 4: Project cost is not updated when result cost is None."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=None
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(0.0)

    def test_outcome_dict_returns_cost(self, tmp_db, project, feature):
        """Step 4: The returned outcome dict contains cost information."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=3.00
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            outcome = handle_execution_result(
                project_id=project.id,
                feature=feature,
                spawn_result=spawn_result,
            )

            assert outcome["cost_usd"] == 3.00


# ============================================================
# Step 5: End-to-end - run feature to completion
# ============================================================


class TestEndToEndFeatureCompletion:
    """Test running a feature to completion verifying status and evidence."""

    @pytest.mark.asyncio
    async def test_execute_feature_creates_evidence(self, tmp_db, project, feature):
        """Step 5: execute_feature creates evidence artifacts upon completion."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            mock_result = ExecutionResult(
                text="Feature implemented. All tests pass.",
                is_error=False,
                duration_ms=8000,
                num_turns=12,
                total_cost_usd=2.00,
                tool_uses=["Read", "Edit", "Bash"],
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ):
                await loop.execute_feature(feature)

            # Verify feature status
            updated = get_feature(feature.id)
            assert updated.status == "completed"

            # Verify evidence was created
            evidence_list = query_evidence(
                project_id=project.id, feature_id=feature.id
            )
            assert len(evidence_list) >= 1
            types = {e.type for e in evidence_list}
            assert "execution_output" in types

    @pytest.mark.asyncio
    async def test_execute_feature_failure_creates_error_evidence(
        self, tmp_db, project, feature
    ):
        """Step 5: execute_feature creates error evidence on failure."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            mock_result = ExecutionResult(
                text="Attempted but failed",
                is_error=True,
                error_message="Compilation error",
                duration_ms=3000,
                num_turns=4,
                total_cost_usd=0.50,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ):
                await loop.execute_feature(feature)

            # Verify feature status
            # F071: First failure resets to 'ready' for retry (not permanently failed)
            updated = get_feature(feature.id)
            assert updated.status == "ready"
            assert updated.refinement_attempts == 1

            # Verify error evidence was created
            evidence_list = query_evidence(
                project_id=project.id, feature_id=feature.id
            )
            assert len(evidence_list) >= 1
            types = {e.type for e in evidence_list}
            assert "execution_error" in types

    @pytest.mark.asyncio
    async def test_execute_feature_updates_project_cost(
        self, tmp_db, project, feature
    ):
        """Step 5: execute_feature updates project total cost."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            mock_result = ExecutionResult(
                text="Done",
                is_error=False,
                duration_ms=1000,
                num_turns=3,
                total_cost_usd=1.75,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ):
                await loop.execute_feature(feature)

            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(1.75)
            assert loop.total_cost == pytest.approx(1.75)

    @pytest.mark.asyncio
    async def test_full_loop_creates_evidence_for_all_features(
        self, tmp_db, project
    ):
        """Step 5: Full loop run creates evidence for each completed feature."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Create 2 ready features
            features = []
            for i in range(2):
                f = create_feature(
                    project_id=project.id,
                    name=f"Feature {i + 1}",
                    description=f"Test feature {i + 1}",
                    status="ready",
                    priority=10 * (i + 1),
                    risk_category="medium",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                features.append(get_feature(f.id))

            loop = OrchestrationLoop(project_id=project.id)
            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_result = ExecutionResult(
                    text=f"Implemented feature {call_count}",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=0.50,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED
            assert call_count == 2

            # Verify evidence for each feature
            for feat in features:
                evidence_list = query_evidence(
                    project_id=project.id, feature_id=feat.id
                )
                assert len(evidence_list) >= 1, (
                    f"No evidence for feature {feat.name}"
                )
