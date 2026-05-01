"""Tests for F118: End-to-end test - Full resume workflow.

E2E test for complete interrupt/resume/spec-change workflow:
Step 1: Start bob3 with 5-feature spec
Step 2: Complete 2 features, interrupt mid-3rd
Step 3: Verify checkpoint created, status='interrupted'
Step 4: Resume bob3, verify continues from feature 3
Step 5: Complete feature 3, interrupt again
Step 6: Modify spec to add feature 6 and change feature 5
Step 7: Resume bob3, verify spec change detected
Step 8: Verify feature 5 reset, feature 6 added
Step 9: Complete all features, verify full success
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from bob3.db import (
    compute_spec_hash,
    create_checkpoint,
    create_feature,
    create_project,
    detect_spec_changes,
    find_resumable_checkpoints,
    get_checkpoint,
    get_feature,
    get_ready_features,
    init_database,
    list_checkpoints,
    list_features,
    query_evidence,
    update_feature,
    update_project,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def spec_file(tmp_path):
    """Create a YAML spec with 5 features."""
    spec = {
        "name": "ResumeWorkflowProject",
        "version": "1.0",
        "features": [
            {
                "name": "Feature 1",
                "description": "First feature",
                "priority": 10,
                "acceptance_criteria": ["Step 1: Implement feature 1"],
            },
            {
                "name": "Feature 2",
                "description": "Second feature",
                "priority": 20,
                "acceptance_criteria": ["Step 1: Implement feature 2"],
            },
            {
                "name": "Feature 3",
                "description": "Third feature",
                "priority": 30,
                "acceptance_criteria": ["Step 1: Implement feature 3"],
            },
            {
                "name": "Feature 4",
                "description": "Fourth feature",
                "priority": 40,
                "acceptance_criteria": ["Step 1: Implement feature 4"],
            },
            {
                "name": "Feature 5",
                "description": "Fifth feature",
                "priority": 50,
                "acceptance_criteria": ["Step 1: Implement feature 5"],
            },
        ],
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.dump(spec, default_flow_style=False))
    return spec_path


@pytest.fixture
def project_with_5_features(tmp_db, spec_file):
    """Create a project with 5 ready features from the spec."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        project = create_project(
            name="ResumeWorkflowProject",
            workspace_path="/tmp/resume-e2e",
            spec_path=str(spec_file),
        )
        spec_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=spec_hash)

        features = []
        for i in range(1, 6):
            f = create_feature(
                project_id=project.id,
                name=f"Feature {i}",
                description=f"{'First' if i==1 else 'Second' if i==2 else 'Third' if i==3 else 'Fourth' if i==4 else 'Fifth'} feature",
                acceptance_criteria=json.dumps([f"Step 1: Implement feature {i}"]),
                status="ready",
                priority=i * 10,
                risk_category="low",
            )
            update_feature(
                f.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            features.append(get_feature(f.id))

        return project, features


def _make_spawn_result(text="Feature done", is_error=False, error_message=None, cost=0.50):
    """Helper to create a SpawnResult with reasonable defaults."""
    mock_result = ExecutionResult(
        text=text,
        is_error=is_error,
        error_message=error_message or ("" if is_error else None),
        duration_ms=3000,
        num_turns=8,
        total_cost_usd=cost,
    )
    mock_agent_run = MagicMock()
    mock_agent_run.id = str(uuid.uuid4())
    return SpawnResult(
        execution_result=mock_result,
        agent_run=mock_agent_run,
    )


# These E2E tests focus on interrupt/resume and spec-change behavior, not on
# post-execution verification of a real workspace. The workspaces used are
# lightweight stubs (/tmp paths) that do not contain implementation files
# matching the mock spec's acceptance criteria, so we stub out the verification
# checklist to always pass. Verification itself is exercised by the dedicated
# superpowers / F113 tests.
def _passing_verification(**_kwargs):
    return {
        "passed": True,
        "checks": [],
        "summary": "Verification stubbed to pass in F118 e2e tests",
    }


class TestE2EStep1StartWith5Features:
    """Step 1: Start bob3 with 5-feature spec."""

    def test_project_has_5_ready_features(self, tmp_db, project_with_5_features):
        """Verify project was created with exactly 5 ready features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features
            assert len(features) == 5

            ready = get_ready_features(project.id)
            assert len(ready) == 5

            for i, f in enumerate(features):
                assert f.name == f"Feature {i + 1}"
                assert f.status == "ready"
                assert f.readiness_score >= 0.7


class TestE2EStep2And3Complete2ThenInterrupt:
    """Steps 2-3: Complete 2 features, interrupt mid-3rd, verify checkpoint."""

    @pytest.mark.asyncio
    async def test_complete_2_interrupt_mid_3rd(self, tmp_db, project_with_5_features):
        """Complete features 1 and 2, then interrupt during feature 3."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/resume-e2e",
            )

            spawn_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_count
                spawn_count += 1

                if spawn_count <= 2:
                    # Features 1 and 2 complete successfully
                    return _make_spawn_result(
                        text=f"Feature {spawn_count} implemented",
                        cost=0.50,
                    )
                else:
                    # Feature 3: simulate shutdown mid-execution
                    loop.request_shutdown()
                    return _make_spawn_result(
                        text="Interrupted during execution",
                        is_error=True,
                        error_message="Shutdown requested",
                        cost=0.30,
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
            ), patch(
                "bob3.orchestrator.run_loop.stop_mcp_server",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                termination = await loop.run()

            # Step 2 verification: 2 features completed, interrupted on 3rd
            assert spawn_count == 3
            assert termination == LoopTermination.SHUTDOWN_REQUESTED

            # Features 1 and 2 should be completed
            assert get_feature(features[0].id).status == "completed"
            assert get_feature(features[1].id).status == "completed"

            # Step 3 verification: Feature 3 should be interrupted with checkpoint
            f3 = get_feature(features[2].id)
            assert f3.status == "interrupted"

            # Checkpoint should exist for feature 3
            checkpoints = list_checkpoints(feature_id=features[2].id)
            assert len(checkpoints) >= 1
            cp = checkpoints[-1]
            assert cp.checkpoint_type == "interruption"
            assert cp.can_resume is True

            # Features 4 and 5 should still be ready
            assert get_feature(features[3].id).status == "ready"
            assert get_feature(features[4].id).status == "ready"


class TestE2EStep4ResumeFromFeature3:
    """Step 4: Resume bob3, verify continues from feature 3."""

    @pytest.mark.asyncio
    async def test_resume_continues_from_feature_3(self, tmp_db, project_with_5_features):
        """After interrupt, resuming should pick up from feature 3."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            # Simulate the state after steps 2-3:
            # Features 1,2 completed; Feature 3 interrupted with checkpoint; 4,5 ready
            update_feature(features[0].id, status="completed")
            update_feature(features[1].id, status="completed")
            update_feature(features[2].id, status="interrupted")

            # Create an interruption checkpoint for feature 3
            state = {
                "feature_id": features[2].id,
                "feature_name": "Feature 3",
                "feature_status": "interrupted",
                "reason": "graceful_shutdown",
            }
            cp = create_checkpoint(
                project_id=project.id,
                feature_id=features[2].id,
                checkpoint_type="interruption",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=1.30,
                duration_at_checkpoint_ms=9000,
            )

            # Start a new orchestration loop (simulates bob3 run after interrupt)
            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/resume-e2e",
            )

            executed_features = []

            async def mock_spawn(*args, **kwargs):
                target_id = kwargs.get("target_id")
                executed_features.append(target_id)
                return _make_spawn_result(
                    text="Feature completed after resume",
                    cost=0.50,
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
                return_value="ghi789",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.ALL_COMPLETED

            # Feature 3 should have been resumed (checkpoint consumed)
            consumed_cp = get_checkpoint(cp.id)
            assert consumed_cp.can_resume is False
            assert consumed_cp.resumed_at is not None

            # Features 3, 4, and 5 should have been executed
            assert len(executed_features) == 3
            assert features[2].id in executed_features
            assert features[3].id in executed_features
            assert features[4].id in executed_features

            # All features should now be completed
            for f in features:
                assert get_feature(f.id).status == "completed"


class TestE2EStep5CompleteFeature3ThenInterruptAgain:
    """Step 5: Complete feature 3, interrupt again."""

    @pytest.mark.asyncio
    async def test_complete_feature3_interrupt_on_feature4(self, tmp_db, project_with_5_features):
        """After resume, complete feature 3, then interrupt on feature 4."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            # State: Features 1,2 completed; 3 interrupted; 4,5 ready
            update_feature(features[0].id, status="completed")
            update_feature(features[1].id, status="completed")
            update_feature(features[2].id, status="interrupted")

            state = {
                "feature_id": features[2].id,
                "feature_name": "Feature 3",
                "feature_status": "interrupted",
                "reason": "graceful_shutdown",
            }
            create_checkpoint(
                project_id=project.id,
                feature_id=features[2].id,
                checkpoint_type="interruption",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=1.30,
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/resume-e2e",
            )

            spawn_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal spawn_count
                spawn_count += 1

                if spawn_count == 1:
                    # Feature 3 completes this time
                    return _make_spawn_result(
                        text="Feature 3 completed",
                        cost=0.50,
                    )
                else:
                    # Feature 4: interrupt again
                    loop.request_shutdown()
                    return _make_spawn_result(
                        text="Interrupted during feature 4",
                        is_error=True,
                        error_message="Shutdown requested",
                        cost=0.30,
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
                return_value="jkl012",
            ), patch(
                "bob3.orchestrator.run_loop.stop_mcp_server",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.SHUTDOWN_REQUESTED
            assert spawn_count == 2

            # Feature 3 completed
            assert get_feature(features[2].id).status == "completed"

            # Feature 4 interrupted
            f4 = get_feature(features[3].id)
            assert f4.status == "interrupted"

            # Feature 4 should have an interruption checkpoint
            checkpoints = list_checkpoints(feature_id=features[3].id)
            assert len(checkpoints) >= 1
            assert checkpoints[-1].checkpoint_type == "interruption"
            assert checkpoints[-1].can_resume is True

            # Feature 5 still ready
            assert get_feature(features[4].id).status == "ready"


class TestE2EStep6And7ModifySpecAndDetect:
    """Steps 6-7: Modify spec (add feature 6, change feature 5), resume and detect."""

    def test_modify_spec_detected(self, tmp_db, spec_file, project_with_5_features):
        """Modifying the spec file is detected by spec change detection."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            # Simulate state: features 1-3 completed, 4 interrupted, 5 ready
            update_feature(features[0].id, status="completed")
            update_feature(features[1].id, status="completed")
            update_feature(features[2].id, status="completed")
            update_feature(features[3].id, status="interrupted")

            # Step 6: Modify spec - change feature 5's description and add feature 6
            spec = yaml.safe_load(spec_file.read_text())
            for f in spec["features"]:
                if f["name"] == "Feature 5":
                    f["description"] = "Updated fifth feature with new requirements"
            spec["features"].append({
                "name": "Feature 6",
                "description": "Sixth feature added in spec change",
                "priority": 60,
                "acceptance_criteria": ["Step 1: Implement feature 6"],
            })
            spec_file.write_text(yaml.dump(spec, default_flow_style=False))

            # Step 7: Detect spec changes
            changes = detect_spec_changes(project.id)
            assert changes is not None

            # Feature 6 should be added
            added_names = [c["name"] for c in changes["added"]]
            assert "Feature 6" in added_names

            # Feature 5 should be modified
            modified_names = [c["name"] for c in changes["modified"]]
            assert "Feature 5" in modified_names


class TestE2EStep8VerifyFeature5ResetAndFeature6Added:
    """Step 8: Verify feature 5 reset to pending, feature 6 added."""

    def test_feature5_reset_and_feature6_added(self, tmp_db, spec_file, project_with_5_features):
        """After spec change detection, feature 5 resets and feature 6 is added."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            # Set up state
            update_feature(features[0].id, status="completed")
            update_feature(features[1].id, status="completed")
            update_feature(features[2].id, status="completed")
            update_feature(features[3].id, status="interrupted")

            # Modify spec
            spec = yaml.safe_load(spec_file.read_text())
            for f in spec["features"]:
                if f["name"] == "Feature 5":
                    f["description"] = "Updated fifth feature with new requirements"
            spec["features"].append({
                "name": "Feature 6",
                "description": "Sixth feature added in spec change",
                "priority": 60,
                "acceptance_criteria": ["Step 1: Implement feature 6"],
            })
            spec_file.write_text(yaml.dump(spec, default_flow_style=False))

            # Detect and apply spec changes
            detect_spec_changes(project.id)

            # Verify feature 5 was reset to pending (modified features reset)
            all_features = list_features(project_id=project.id)
            f5_candidates = [f for f in all_features if f.name == "Feature 5"]
            assert len(f5_candidates) >= 1
            f5 = f5_candidates[0]
            assert f5.status == "pending"

            # Verify feature 6 was added
            f6_candidates = [f for f in all_features if f.name == "Feature 6"]
            assert len(f6_candidates) == 1
            f6 = f6_candidates[0]
            assert f6.project_id == project.id

            # Verify the spec hash was updated
            from bob3.db import get_project
            updated_project = get_project(project.id)
            new_hash = compute_spec_hash(spec_file)
            assert updated_project.spec_hash == new_hash


class TestE2EStep9FullWorkflow:
    """Step 9: Full end-to-end workflow - complete all features, verify full success."""

    @pytest.mark.asyncio
    async def test_full_interrupt_resume_spec_change_workflow(self, tmp_db, tmp_path):
        """Complete end-to-end test exercising all 9 steps.

        This test exercises the complete lifecycle:
        1. Create project with 5-feature spec
        2. Complete 2 features, interrupt mid-3rd
        3. Verify checkpoint created, feature 3 status='interrupted'
        4. Resume, verify continues from feature 3
        5. Complete feature 3, interrupt on feature 4
        6. Modify spec to add feature 6 and change feature 5
        7. Resume, verify spec change detected
        8. Verify feature 5 reset, feature 6 added
        9. Complete all remaining features, verify full success
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # ---- STEP 1: Create project with 5-feature spec ----
            spec = {
                "name": "FullWorkflowProject",
                "version": "1.0",
                "features": [
                    {
                        "name": f"Feature {i}",
                        "description": f"Feature {i} description",
                        "priority": i * 10,
                        "acceptance_criteria": [f"Implement feature {i}"],
                    }
                    for i in range(1, 6)
                ],
            }
            spec_path = tmp_path / "workflow_spec.yaml"
            spec_path.write_text(yaml.dump(spec, default_flow_style=False))

            project = create_project(
                name="FullWorkflowProject",
                workspace_path="/tmp/full-e2e",
                spec_path=str(spec_path),
            )
            spec_hash = compute_spec_hash(spec_path)
            update_project(project.id, spec_hash=spec_hash)

            features = []
            for i in range(1, 6):
                f = create_feature(
                    project_id=project.id,
                    name=f"Feature {i}",
                    description=f"Feature {i} description",
                    acceptance_criteria=json.dumps([f"Implement feature {i}"]),
                    status="ready",
                    priority=i * 10,
                    risk_category="low",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                features.append(get_feature(f.id))

            assert len(features) == 5
            assert len(get_ready_features(project.id)) == 5

            # ---- STEP 2: Complete 2 features, interrupt mid-3rd ----
            loop1 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/full-e2e",
            )

            loop1_spawn_count = 0

            async def mock_spawn_phase1(*args, **kwargs):
                nonlocal loop1_spawn_count
                loop1_spawn_count += 1

                if loop1_spawn_count <= 2:
                    return _make_spawn_result(
                        text=f"Feature {loop1_spawn_count} done",
                        cost=0.50,
                    )
                else:
                    loop1.request_shutdown()
                    return _make_spawn_result(
                        text="Interrupted",
                        is_error=True,
                        error_message="Shutdown requested",
                        cost=0.30,
                    )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_phase1,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ), patch(
                "bob3.orchestrator.run_loop.stop_mcp_server",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                term1 = await loop1.run()

            assert term1 == LoopTermination.SHUTDOWN_REQUESTED
            assert loop1_spawn_count == 3

            # ---- STEP 3: Verify checkpoint created, status='interrupted' ----
            assert get_feature(features[0].id).status == "completed"
            assert get_feature(features[1].id).status == "completed"

            f3_after = get_feature(features[2].id)
            assert f3_after.status == "interrupted"

            f3_checkpoints = list_checkpoints(feature_id=features[2].id)
            assert len(f3_checkpoints) >= 1
            f3_cp = f3_checkpoints[-1]
            assert f3_cp.checkpoint_type == "interruption"
            assert f3_cp.can_resume is True

            # ---- STEP 4: Resume bob3, verify continues from feature 3 ----
            loop2 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/full-e2e",
            )

            loop2_spawn_count = 0

            async def mock_spawn_phase2(*args, **kwargs):
                nonlocal loop2_spawn_count
                loop2_spawn_count += 1

                if loop2_spawn_count == 1:
                    # Feature 3 completes
                    return _make_spawn_result(
                        text="Feature 3 completed on resume",
                        cost=0.50,
                    )
                else:
                    # Feature 4: interrupt again (step 5)
                    loop2.request_shutdown()
                    return _make_spawn_result(
                        text="Interrupted on feature 4",
                        is_error=True,
                        error_message="Shutdown requested",
                        cost=0.30,
                    )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_phase2,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="ghi789",
            ), patch(
                "bob3.orchestrator.run_loop.stop_mcp_server",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                term2 = await loop2.run()

            # Checkpoint from step 3 should have been consumed
            consumed_cp = get_checkpoint(f3_cp.id)
            assert consumed_cp.can_resume is False

            # ---- STEP 5: Complete feature 3, interrupt again on feature 4 ----
            assert term2 == LoopTermination.SHUTDOWN_REQUESTED
            assert loop2_spawn_count == 2

            assert get_feature(features[2].id).status == "completed"

            f4_after = get_feature(features[3].id)
            assert f4_after.status == "interrupted"

            f4_checkpoints = list_checkpoints(feature_id=features[3].id)
            assert len(f4_checkpoints) >= 1
            f4_cp = f4_checkpoints[-1]
            assert f4_cp.can_resume is True

            # Feature 5 still ready
            assert get_feature(features[4].id).status == "ready"

            # ---- STEP 6: Modify spec to add feature 6 and change feature 5 ----
            spec["features"] = [
                {"name": "Feature 1", "description": "Feature 1 description", "priority": 10, "acceptance_criteria": ["Implement feature 1"]},
                {"name": "Feature 2", "description": "Feature 2 description", "priority": 20, "acceptance_criteria": ["Implement feature 2"]},
                {"name": "Feature 3", "description": "Feature 3 description", "priority": 30, "acceptance_criteria": ["Implement feature 3"]},
                {"name": "Feature 4", "description": "Feature 4 description", "priority": 40, "acceptance_criteria": ["Implement feature 4"]},
                {"name": "Feature 5", "description": "Updated feature 5 with new requirements", "priority": 50, "acceptance_criteria": ["Implement feature 5"]},
                {"name": "Feature 6", "description": "Brand new feature 6", "priority": 60, "acceptance_criteria": ["Implement feature 6"]},
            ]
            spec_path.write_text(yaml.dump(spec, default_flow_style=False))

            # ---- STEP 7: Resume bob3, verify spec change detected ----
            changes = detect_spec_changes(project.id)
            assert changes is not None

            added_names = [c["name"] for c in changes["added"]]
            modified_names = [c["name"] for c in changes["modified"]]

            assert "Feature 6" in added_names
            assert "Feature 5" in modified_names

            # ---- STEP 8: Verify feature 5 reset, feature 6 added ----
            all_features_after_spec = list_features(project_id=project.id)
            feature_map = {f.name: f for f in all_features_after_spec}

            # Feature 5 should have been reset to pending (spec changed)
            assert "Feature 5" in feature_map
            assert feature_map["Feature 5"].status == "pending"

            # Feature 6 should be added
            assert "Feature 6" in feature_map
            assert feature_map["Feature 6"].project_id == project.id

            # Completed features remain completed
            assert feature_map["Feature 1"].status == "completed"
            assert feature_map["Feature 2"].status == "completed"
            assert feature_map["Feature 3"].status == "completed"

            # Set feature 5 and 6 to ready (simulating bob3 plan/readiness assessment)
            f5 = feature_map["Feature 5"]
            f6 = feature_map["Feature 6"]
            for fid in (f5.id, f6.id):
                update_feature(
                    fid,
                    status="ready",
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )

            # Also re-ready feature 4 (it was interrupted, will be resumed)
            # The loop's _resume_interrupted_work handles this automatically

            # ---- STEP 9: Complete all remaining features, verify full success ----
            loop3 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/full-e2e",
            )

            loop3_executed = []

            async def mock_spawn_phase3(*args, **kwargs):
                target_id = kwargs.get("target_id")
                loop3_executed.append(target_id)
                return _make_spawn_result(
                    text="Feature completed",
                    cost=0.50,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_phase3,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="mno345",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                term3 = await loop3.run()

            assert term3 == LoopTermination.ALL_COMPLETED

            # Feature 4's checkpoint should be consumed
            f4_cp_final = get_checkpoint(f4_cp.id)
            assert f4_cp_final.can_resume is False

            # All features should be completed now
            final_features = list_features(project_id=project.id)
            for f in final_features:
                assert f.status == "completed", (
                    f"Feature {f.name} should be completed but is {f.status}"
                )

            # All executed features in phase 3 should include feature 4, 5, and 6
            assert len(loop3_executed) == 3
            expected_ids = {
                feature_map["Feature 4"].id,
                feature_map["Feature 5"].id,
                feature_map["Feature 6"].id,
            }
            assert set(loop3_executed) == expected_ids

            # Evidence should exist for every feature
            for f in final_features:
                evidence = query_evidence(feature_id=f.id)
                assert len(evidence) >= 1, (
                    f"Feature {f.name} should have at least one evidence artifact"
                )


class TestE2ESpecChangeWithCompletedFeatures:
    """Edge case: spec change doesn't affect already-completed features."""

    def test_completed_features_not_affected_by_spec_change(
        self, tmp_db, spec_file, project_with_5_features
    ):
        """Completed features remain completed even when spec changes."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            # Complete features 1 and 2
            update_feature(features[0].id, status="completed")
            update_feature(features[1].id, status="completed")

            # Modify spec: only change feature 3 description
            spec = yaml.safe_load(spec_file.read_text())
            for f in spec["features"]:
                if f["name"] == "Feature 3":
                    f["description"] = "Modified feature 3 description"
            spec_file.write_text(yaml.dump(spec, default_flow_style=False))

            detect_spec_changes(project.id)

            # Features 1 and 2 still completed
            assert get_feature(features[0].id).status == "completed"
            assert get_feature(features[1].id).status == "completed"

            # Feature 3 should be reset (modified)
            f3 = get_feature(features[2].id)
            assert f3.status == "pending"


class TestE2EMultipleInterruptResumeCycles:
    """Test multiple interrupt-resume cycles work correctly."""

    @pytest.mark.asyncio
    async def test_three_interrupt_resume_cycles(self, tmp_db, project_with_5_features):
        """Three interrupt-resume cycles all work correctly."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project, features = project_with_5_features

            # Cycle 1: Execute feature 1, interrupt on feature 2
            loop1 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/resume-e2e",
            )
            cycle1_count = 0

            async def mock_cycle1(*args, **kwargs):
                nonlocal cycle1_count
                cycle1_count += 1
                if cycle1_count == 1:
                    return _make_spawn_result(text="Feature 1 done", cost=0.50)
                loop1.request_shutdown()
                return _make_spawn_result(
                    text="Interrupted", is_error=True,
                    error_message="Shutdown requested", cost=0.20,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock, side_effect=mock_cycle1,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="c1",
            ), patch("bob3.orchestrator.run_loop.stop_mcp_server"), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                t1 = await loop1.run()

            assert t1 == LoopTermination.SHUTDOWN_REQUESTED
            assert get_feature(features[0].id).status == "completed"
            assert get_feature(features[1].id).status == "interrupted"

            # Cycle 2: Resume feature 2, complete it, complete feature 3,
            # interrupt on feature 4
            loop2 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/resume-e2e",
            )
            cycle2_count = 0

            async def mock_cycle2(*args, **kwargs):
                nonlocal cycle2_count
                cycle2_count += 1
                if cycle2_count <= 2:
                    return _make_spawn_result(
                        text=f"Feature done ({cycle2_count})", cost=0.50,
                    )
                loop2.request_shutdown()
                return _make_spawn_result(
                    text="Interrupted", is_error=True,
                    error_message="Shutdown requested", cost=0.20,
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock, side_effect=mock_cycle2,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "def"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="c2",
            ), patch("bob3.orchestrator.run_loop.stop_mcp_server"), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                t2 = await loop2.run()

            assert t2 == LoopTermination.SHUTDOWN_REQUESTED
            assert get_feature(features[0].id).status == "completed"
            assert get_feature(features[1].id).status == "completed"
            assert get_feature(features[2].id).status == "completed"
            assert get_feature(features[3].id).status == "interrupted"

            # Cycle 3: Resume feature 4, complete everything
            loop3 = OrchestrationLoop(
                project_id=project.id,
                workspace="/tmp/resume-e2e",
            )

            async def mock_cycle3(*args, **kwargs):
                return _make_spawn_result(text="Feature done", cost=0.50)

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock, side_effect=mock_cycle3,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "ghi"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="c3",
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_passing_verification,
            ):
                t3 = await loop3.run()

            assert t3 == LoopTermination.ALL_COMPLETED

            # All 5 features should be completed
            for f in features:
                assert get_feature(f.id).status == "completed"
