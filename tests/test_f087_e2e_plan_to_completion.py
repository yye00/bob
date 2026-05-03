"""Tests for F087: End-to-end test - Plan from spec file, run to completion.

End-to-end integration test that exercises the full Bob3 workflow from
spec file to completion with a 3-feature dependency chain:

Step 1: Create test spec YAML with 3 features (A->B->C dependency chain)
Step 2: Run bob3 plan test-spec.yaml --create
Step 3: Verify 3 features created in database
Step 4: Run bob3 run in loop until all features complete
Step 5: Verify all features reach status=completed
Step 6: Verify dependencies were respected (A before B before C)
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from bob3.cli import main
from bob3.db import (
    connect,
    create_project,
    get_feature,
    get_feature_dependencies,
    get_ready_features,
    init_database,
    list_features,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import LoopTermination, OrchestrationLoop


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "bob3.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path), \
         patch("bob3.cli.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory for the project."""
    ws = tmp_path / "e2e-project"
    ws.mkdir()
    return ws


@pytest.fixture
def spec_file(tmp_path):
    """Create a test spec YAML with 3 features in A->B->C dependency chain."""
    spec = {
        "name": "e2e-test-project",
        "version": "1.0.0",
        "features": [
            {
                "name": "Feature A",
                "description": "Foundation feature with no dependencies",
                "priority": 10,
                "acceptance_criteria": [
                    "File exists: feature_a.txt",
                ],
            },
            {
                "name": "Feature B",
                "description": "Depends on Feature A",
                "priority": 20,
                "acceptance_criteria": [
                    "File exists: feature_b.txt",
                ],
                "depends_on": ["Feature A"],
            },
            {
                "name": "Feature C",
                "description": "Depends on Feature B",
                "priority": 30,
                "acceptance_criteria": [
                    "File exists: feature_c.txt",
                ],
                "depends_on": ["Feature B"],
            },
        ],
    }
    spec_path = tmp_path / "test-spec.yaml"
    spec_path.write_text(yaml.dump(spec, default_flow_style=False))
    return spec_path


class TestE2ECreateSpecYAML:
    """Step 1: Create test spec YAML with 3 features (A->B->C dependency chain)."""

    def test_spec_yaml_has_three_features(self, spec_file):
        """The spec YAML contains exactly 3 features."""
        with open(spec_file) as f:
            spec = yaml.safe_load(f)
        assert len(spec["features"]) == 3

    def test_spec_yaml_has_dependency_chain(self, spec_file):
        """Features B depends on A, C depends on B."""
        with open(spec_file) as f:
            spec = yaml.safe_load(f)
        features = spec["features"]
        # A has no dependencies
        assert "depends_on" not in features[0]
        # B depends on A
        assert features[1]["depends_on"] == ["Feature A"]
        # C depends on B
        assert features[2]["depends_on"] == ["Feature B"]


class TestE2EPlanFromSpec:
    """Step 2: Run bob3 plan test-spec.yaml --create.
    Step 3: Verify 3 features created in database."""

    def test_plan_create_inserts_three_features(self, tmp_db, spec_file):
        """bob3 plan --create inserts 3 features into the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Create a project first (plan command reads the project)
            project = create_project(
                name="e2e-test-project",
                workspace_path="/tmp/e2e-project",
            )

            runner = CliRunner()
            result = runner.invoke(
                main, ["plan", str(spec_file), "--create"]
            )
            assert result.exit_code == 0
            assert "Created 3 features" in result.output

            # Verify features exist in database
            features = list_features(project_id=project.id)
            assert len(features) == 3

            names = [f.name for f in features]
            assert "Feature A" in names
            assert "Feature B" in names
            assert "Feature C" in names

    def test_plan_create_establishes_dependencies(self, tmp_db, spec_file):
        """bob3 plan --create creates correct dependency relationships."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="e2e-test-project",
                workspace_path="/tmp/e2e-project",
            )

            runner = CliRunner()
            result = runner.invoke(
                main, ["plan", str(spec_file), "--create"]
            )
            assert result.exit_code == 0

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            # Feature A has no dependencies
            deps_a = get_feature_dependencies(by_name["Feature A"].id)
            assert len(deps_a) == 0

            # Feature B depends on Feature A
            deps_b = get_feature_dependencies(by_name["Feature B"].id)
            assert len(deps_b) == 1
            assert deps_b[0].depends_on_feature_id == by_name["Feature A"].id

            # Feature C depends on Feature B
            deps_c = get_feature_dependencies(by_name["Feature C"].id)
            assert len(deps_c) == 1
            assert deps_c[0].depends_on_feature_id == by_name["Feature B"].id

    def test_plan_create_sets_priorities(self, tmp_db, spec_file):
        """Features are created with correct priorities from the spec."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="e2e-test-project",
                workspace_path="/tmp/e2e-project",
            )

            runner = CliRunner()
            runner.invoke(main, ["plan", str(spec_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            assert by_name["Feature A"].priority == 10
            assert by_name["Feature B"].priority == 20
            assert by_name["Feature C"].priority == 30


class TestE2ERunToCompletion:
    """Step 4-6: Run orchestration loop, verify completion and dependency order."""

    @pytest.mark.asyncio
    async def test_full_plan_to_completion(self, tmp_db, workspace, spec_file):
        """Full E2E: plan spec -> create features -> run loop -> all completed.

        This is the main integration test that exercises the complete workflow.
        It creates the spec, creates features with dependencies (A->B->C),
        runs the orchestration loop, and verifies:
        - All features reach 'completed' status
        - Dependencies were respected (A completed before B, B before C)
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Step 1-2: Create project and features from spec
            project = create_project(
                name="e2e-test-project",
                workspace_path=str(workspace),
            )

            runner = CliRunner()
            result = runner.invoke(
                main, ["plan", str(spec_file), "--create"]
            )
            assert result.exit_code == 0

            features = list_features(project_id=project.id)
            assert len(features) == 3
            by_name = {f.name: f for f in features}

            # Set up features for orchestration:
            # Feature A: status=ready, high readiness (no deps, can run immediately)
            # Feature B: status=pending, high readiness (deps on A, cascade will make ready)
            # Feature C: status=pending, high readiness (deps on B, cascade will make ready)
            update_feature(
                by_name["Feature A"].id,
                status="ready",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            update_feature(
                by_name["Feature B"].id,
                status="pending",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            update_feature(
                by_name["Feature C"].id,
                status="pending",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            # Verify initial state: only Feature A is ready (B and C are pending)
            ready = get_ready_features(project.id)
            assert len(ready) == 1
            assert ready[0].name == "Feature A"

            # Track execution order to verify dependency respect
            execution_order = []

            async def mock_spawn(*args, **kwargs):
                target_id = kwargs.get("target_id")
                feature = get_feature(target_id)
                execution_order.append(feature.name)

                # Simulate the sub-agent producing the artifact expected by
                # the feature's "File exists: feature_X.txt" acceptance criterion.
                suffix = feature.name.rsplit(" ", 1)[-1].lower()
                (workspace / f"feature_{suffix}.txt").write_text("implemented")

                mock_result = ExecutionResult(
                    text=f"{feature.name} implemented successfully.",
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

            # Step 4: Run orchestration loop
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
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

            # Step 5: Verify all features reach status=completed
            assert termination == LoopTermination.ALL_COMPLETED

            for name in ["Feature A", "Feature B", "Feature C"]:
                f = get_feature(by_name[name].id)
                assert f.status == "completed", (
                    f"{name} should be completed, got {f.status}"
                )

            # Step 6: Verify dependencies were respected (A before B before C)
            assert len(execution_order) == 3
            assert execution_order.index("Feature A") < execution_order.index(
                "Feature B"
            ), "Feature A must be executed before Feature B"
            assert execution_order.index("Feature B") < execution_order.index(
                "Feature C"
            ), "Feature B must be executed before Feature C"

    @pytest.mark.asyncio
    async def test_dependency_chain_blocks_until_ready(self, tmp_db, workspace, spec_file):
        """Features with unmet dependencies are not picked up by the loop."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="e2e-test-project",
                workspace_path=str(workspace),
            )

            runner = CliRunner()
            runner.invoke(main, ["plan", str(spec_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            # Only set Feature A to ready; B and C are pending
            update_feature(
                by_name["Feature A"].id,
                status="ready",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            # B and C have high readiness but are pending (blocked by deps)
            for name in ["Feature B", "Feature C"]:
                update_feature(
                    by_name[name].id,
                    status="pending",
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )

            # Before running: only A should be ready
            ready = get_ready_features(project.id)
            ready_names = [f.name for f in ready]
            assert "Feature A" in ready_names
            assert "Feature B" not in ready_names
            assert "Feature C" not in ready_names

    @pytest.mark.asyncio
    async def test_cascade_unlocks_dependent_features(self, tmp_db, workspace, spec_file):
        """Completing Feature A cascades to make Feature B ready."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="e2e-test-project",
                workspace_path=str(workspace),
            )

            runner = CliRunner()
            runner.invoke(main, ["plan", str(spec_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            # Set A to completed, B to pending with high readiness
            update_feature(
                by_name["Feature A"].id,
                status="completed",
                readiness_score=0.9,
            )
            update_feature(
                by_name["Feature B"].id,
                status="pending",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            update_feature(
                by_name["Feature C"].id,
                status="pending",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            # Manually trigger cascade (this is what the loop does after completing A)
            from bob3.orchestrator.run_loop import cascade_update_dependents

            transitioned = cascade_update_dependents(by_name["Feature A"].id)

            # B should now be ready (its only dep A is completed)
            assert by_name["Feature B"].id in transitioned
            b = get_feature(by_name["Feature B"].id)
            assert b.status == "ready"

            # C should still be pending (its dep B is not yet completed)
            assert by_name["Feature C"].id not in transitioned
            c = get_feature(by_name["Feature C"].id)
            assert c.status == "pending"


class TestE2ECostTracking:
    """Verify cost tracking works across the full dependency chain."""

    @pytest.mark.asyncio
    async def test_total_cost_accumulates_across_chain(self, tmp_db, workspace, spec_file):
        """Total cost accumulates across all 3 features in the chain."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import get_project

            project = create_project(
                name="e2e-test-project",
                workspace_path=str(workspace),
            )

            runner = CliRunner()
            runner.invoke(main, ["plan", str(spec_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            update_feature(
                by_name["Feature A"].id,
                status="ready",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            for name in ["Feature B", "Feature C"]:
                update_feature(
                    by_name[name].id,
                    status="pending",
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )

            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # Simulate producing the artifact expected by the feature's
                # "File exists: feature_X.txt" acceptance criterion.
                target_id = kwargs.get("target_id")
                if target_id is not None:
                    feature = get_feature(target_id)
                    suffix = feature.name.rsplit(" ", 1)[-1].lower()
                    (workspace / f"feature_{suffix}.txt").write_text("implemented")
                mock_result = ExecutionResult(
                    text=f"Feature {call_count} done.",
                    is_error=False,
                    duration_ms=1000,
                    num_turns=5,
                    total_cost_usd=1.00,
                )
                mock_agent_run = MagicMock()
                mock_agent_run.id = str(uuid.uuid4())
                return SpawnResult(
                    execution_result=mock_result,
                    agent_run=mock_agent_run,
                )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
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

            # 3 features at $1.00 each = $3.00 total
            assert call_count == 3
            updated_project = get_project(project.id)
            assert updated_project.total_cost_usd == pytest.approx(3.00)
            # ``self.total_cost`` was retired by the ``non-atomic-counter``
            # structural fix. The cached mirror must equal the DB total.
            assert loop._project_total_cost == pytest.approx(
                updated_project.total_cost_usd
            )
            assert not hasattr(loop, "total_cost")


class TestE2EEvidenceCreation:
    """Verify evidence artifacts are created for each feature."""

    @pytest.mark.asyncio
    async def test_evidence_created_for_all_features(self, tmp_db, workspace, spec_file):
        """Each completed feature should have evidence artifacts."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import query_evidence

            project = create_project(
                name="e2e-test-project",
                workspace_path=str(workspace),
            )

            runner = CliRunner()
            runner.invoke(main, ["plan", str(spec_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            update_feature(
                by_name["Feature A"].id,
                status="ready",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            for name in ["Feature B", "Feature C"]:
                update_feature(
                    by_name[name].id,
                    status="pending",
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )

            async def mock_spawn(*args, **kwargs):
                target_id = kwargs.get("target_id")
                feature = get_feature(target_id)
                # Simulate producing the artifact expected by the feature's
                # "File exists: feature_X.txt" acceptance criterion.
                suffix = feature.name.rsplit(" ", 1)[-1].lower()
                (workspace / f"feature_{suffix}.txt").write_text("implemented")
                mock_result = ExecutionResult(
                    text=f"{feature.name} implemented successfully.",
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

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(workspace),
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

            assert termination == LoopTermination.ALL_COMPLETED

            # Each feature should have execution_output evidence
            for name in ["Feature A", "Feature B", "Feature C"]:
                evidence = query_evidence(feature_id=by_name[name].id)
                assert len(evidence) >= 1, f"{name} should have evidence"
                output_evidence = [
                    e for e in evidence if e.type == "execution_output"
                ]
                assert len(output_evidence) >= 1, (
                    f"{name} should have execution_output evidence"
                )
                content = json.loads(output_evidence[0].content)
                assert content["status"] == "completed"


class TestE2ECLIPlanThenRun:
    """Test the full CLI flow: plan --create then run --all."""

    def test_plan_then_run_via_cli(self, tmp_path, spec_file):
        """CLI plan --create + run --all works end-to-end."""
        project_path = tmp_path / "e2e-test-project"
        runner = CliRunner()

        # Step 1: Init project via CLI
        with patch("bob3.cli.start_mcp_server"):
            result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0

        db_path = project_path / "bob3.db"

        # Step 2: Plan with --create
        with patch("bob3.db.get_database_path", return_value=db_path), \
             patch("bob3.cli.get_database_path", return_value=db_path):
            result = runner.invoke(
                main, ["plan", str(spec_file), "--create"]
            )
        assert result.exit_code == 0
        assert "Created 3 features" in result.output

        # Step 3: Run via CLI (mock the orchestration loop)
        with patch("bob3.db.get_database_path", return_value=db_path), \
             patch("bob3.cli.get_database_path", return_value=db_path):
            with patch("bob3.cli.start_mcp_server"):
                with patch(
                    "bob3.cli._run_orchestration_loop",
                    return_value=LoopTermination.ALL_COMPLETED,
                ) as mock_loop:
                    result = runner.invoke(main, ["run", "--all"])
                    assert result.exit_code == 0
                    mock_loop.assert_called_once()
                    assert "completed" in result.output.lower()
