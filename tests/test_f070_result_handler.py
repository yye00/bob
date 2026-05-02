"""Tests for F070: Handle feature execution results in orchestration loop.

Tests that the orchestration loop properly:
- Parses sub-agent results (success/failure)
- Updates feature status (completed/failed)
- Creates evidence artifacts from results
- Updates cost tracking
- Runs feature to completion with status and evidence updated
"""

import asyncio
import json
import pathlib
import stat
import subprocess
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    add_feature_dependency,
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
            # When the SDK returns None, handle_execution_result now falls
            # back to the turn-count proxy ($0.05/turn × 2 turns = $0.10)
            # so that budget enforcement still works on Max Pro / OAuth
            # subscriptions that don't report cost.
            assert outcome["cost_usd"] == pytest.approx(0.10)
            assert outcome["cost_source"] == "turn_proxy"


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

    def test_cost_zero_when_no_cost_no_turns(self, tmp_db, project, feature):
        """Step 4: When cost is None AND num_turns=0, no cost is recorded.

        Renamed from ``test_cost_not_updated_when_none`` to make explicit
        what this test actually verifies. The original name implied "None
        cost is never recorded," but the call path is:
          ``_normalize_cost(None, 0) -> (0.0, "zero")``
        i.e. zero turns means zero proxy cost. The companion test
        ``test_cost_uses_proxy_when_only_turns_known`` covers the path
        where cost is None but ``num_turns > 0`` and the proxy DOES kick
        in.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=None, num_turns=0
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

    def test_cost_uses_proxy_when_only_turns_known(
        self, tmp_db, project, feature, monkeypatch
    ):
        """Step 4: When cost is None but ``num_turns > 0`` (Claude Max Pro
        / OAuth subscription path), the project cost is still recorded
        using the per-turn proxy.

        This is the actual behaviour the previous test gave a false-pass
        on. With ``num_turns=5`` and the default proxy of $0.05/turn the
        recorded cost should be exactly 0.25 USD. We pin the proxy via
        ``BOB3_COST_PER_TURN_PROXY`` so the assertion is independent of
        environmental defaults.
        """
        # Pin the proxy rate to the documented default so this test is
        # not at the mercy of environment-level overrides.
        monkeypatch.setenv("BOB3_COST_PER_TURN_PROXY", "0.05")

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Capture the cost BEFORE the call so we are asserting on
            # the *delta* and not on assumptions about prior state.
            before = get_project(project.id).total_cost_usd or 0.0

            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=None, num_turns=5
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

            after = get_project(project.id).total_cost_usd or 0.0
            # 5 turns * $0.05/turn = $0.25 proxy charge.
            assert (after - before) == pytest.approx(0.25)

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
            # Bug 1 (2026-04): loop.total_cost is no longer incremented in
            # execute_feature; the DB total is the canonical accumulator.
            assert loop.total_cost <= updated_project.total_cost_usd + 1e-9

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


# ============================================================
# Atomicity: complete_feature_and_cascade rolls back on partial failure
# ============================================================


class TestCompleteFeatureAndCascadeAtomicity:
    """The new atomic helper must roll back the status flip if the cascade
    half raises. Otherwise a crash mid-call leaves the feature 'completed'
    while dependents stay 'pending' forever — exactly the bug this fixes.
    """

    def _make_two_feature_chain(self, project):
        """A → B (B depends on A). A starts in 'ready', B in 'pending'."""
        from bob3.db import add_feature_dependency

        feat_a = create_feature(
            project_id=project.id,
            name="A",
            description="upstream",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            feat_a.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        feat_b = create_feature(
            project_id=project.id,
            name="B",
            description="downstream",
            status="pending",
            priority=20,
            risk_category="medium",
        )
        update_feature(
            feat_b.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )
        add_feature_dependency(
            feature_id=feat_b.id, depends_on_feature_id=feat_a.id
        )
        return get_feature(feat_a.id), get_feature(feat_b.id)

    def test_happy_path_marks_completed_and_cascades(self, tmp_db, project):
        """Sanity: the atomic helper actually does what update_feature +
        update_dependent_features_readiness used to do, but in one tx."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import complete_feature_and_cascade

            feat_a, feat_b = self._make_two_feature_chain(project)
            promoted = complete_feature_and_cascade(feat_a.id)

            assert get_feature(feat_a.id).status == "completed"
            assert get_feature(feat_b.id).status == "ready"
            assert promoted == [feat_b.id]

    def test_rollback_when_cascade_raises_keeps_feature_uncompleted(
        self, tmp_db, project
    ):
        """If the cascade SQL raises, the whole transaction rolls back and
        the feature is NOT marked completed. This is the load-bearing
        invariant: no partial writes survive a crash."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            import bob3.db as db_mod

            feat_a, feat_b = self._make_two_feature_chain(project)
            assert get_feature(feat_a.id).status == "ready"

            # Wrap the connection in a proxy whose ``execute`` raises on
            # the SECOND call (the dependent-lookup, after the status
            # update). The status update already wrote, so rollback is
            # the only thing that can keep the invariant.
            #
            # sqlite3.Connection.execute is a read-only attribute, so we
            # cannot monkey-patch the connection in place. Wrapping is
            # fine because complete_feature_and_cascade only uses
            # ``execute`` and the context-manager protocol.
            original_connect = db_mod.connect

            from contextlib import contextmanager

            class _FlakyConn:
                def __init__(self, real_conn):
                    self._real = real_conn
                    self._calls = 0

                def execute(self, sql, *a, **kw):
                    self._calls += 1
                    if self._calls == 2:
                        raise RuntimeError("simulated crash mid-cascade")
                    return self._real.execute(sql, *a, **kw)

                # Pass-through everything else (commit/rollback are
                # driven by the outer context manager, not us).
                def __getattr__(self, name):
                    return getattr(self._real, name)

            @contextmanager
            def flaky_connect(**kwargs):
                with original_connect(**kwargs) as real_conn:
                    yield _FlakyConn(real_conn)

            with patch.object(db_mod, "connect", flaky_connect):
                with pytest.raises(RuntimeError, match="simulated crash"):
                    db_mod.complete_feature_and_cascade(feat_a.id)

            # The feature must NOT have been marked completed; the
            # transaction rolled back. Dependent must still be pending.
            assert get_feature(feat_a.id).status == "ready"
            assert get_feature(feat_b.id).status == "pending"

    def _make_three_feature_fanout(self, project):
        """A → B and A → C (B and C both depend on A).

        A starts in 'ready'; B and C start in 'pending'. The cascade,
        if it ran to completion, would flip BOTH B and C to 'ready'.
        """
        from bob3.db import add_feature_dependency

        feat_a = create_feature(
            project_id=project.id,
            name="A",
            description="upstream",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            feat_a.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
            readiness_score=0.9,
        )

        dependents: list = []
        for label, prio in [("B", 20), ("C", 30)]:
            f = create_feature(
                project_id=project.id,
                name=label,
                description=f"downstream {label}",
                status="pending",
                priority=prio,
                risk_category="medium",
            )
            update_feature(
                f.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            add_feature_dependency(
                feature_id=f.id, depends_on_feature_id=feat_a.id
            )
            dependents.append(get_feature(f.id))
        return get_feature(feat_a.id), dependents[0], dependents[1]

    def test_rollback_when_cascade_partway_through_multiple_dependents(
        self, tmp_db, project
    ):
        """Atomicity invariant for multi-dependent cascades.

        The ``_FlakyConn`` test above only exercises a chain with ONE
        dependent (A → B), and crashes BEFORE any dependent UPDATE has
        run. That proves "crash before any dependent write rolls back",
        but does NOT prove the bigger invariant we actually care about:

            "Crash partway through a multi-dependent cascade rolls back
             ALL writes — including dependents that already had their
             UPDATE executed before the crash."

        Set up A → B and A → C and crash AFTER one dependent UPDATE has
        run but BEFORE the other's. The rollback must restore the entire
        transaction to its pre-call state — A is still 'ready' (NOT
        'completed'), and BOTH dependents are still 'pending' (the one
        whose UPDATE already executed must be rolled back too).
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            import bob3.db as db_mod

            feat_a, feat_b, feat_c = self._make_three_feature_fanout(project)
            assert get_feature(feat_a.id).status == "ready"
            assert get_feature(feat_b.id).status == "pending"
            assert get_feature(feat_c.id).status == "pending"

            original_connect = db_mod.connect

            from contextlib import contextmanager

            # Trace every SQL statement so we can crash at a specific
            # point — namely, AFTER the FIRST dependent UPDATE has run.
            #
            # Expected execute() sequence in
            # ``complete_feature_and_cascade`` for a 2-dependent fanout:
            #   1. UPDATE features SET status='completed' WHERE id=A
            #   2. SELECT feature_id, depends_on_feature_id FROM
            #      feature_dependencies WHERE depends_on_feature_id=A
            #      (returns 2 rows: one for B, one for C)
            #   3. SELECT all-deps lookup for first dependent
            #   4. UPDATE features SET status='ready' for first dependent
            #   5. SELECT all-deps lookup for second dependent
            #   6. UPDATE features SET status='ready' for second dependent
            #
            # We crash on call 5 — after the first dependent's UPDATE
            # has hit the connection but before the second dependent's
            # UPDATE has even been considered. Rollback must undo the
            # call-1 UPDATE (A) AND the call-4 UPDATE (first dependent).
            class _CrashAfterFirstDependentUpdate:
                def __init__(self, real_conn):
                    self._real = real_conn
                    self._calls = 0

                def execute(self, sql, *a, **kw):
                    self._calls += 1
                    if self._calls == 5:
                        raise RuntimeError(
                            "simulated crash after first dependent UPDATE"
                        )
                    return self._real.execute(sql, *a, **kw)

                def __getattr__(self, name):
                    return getattr(self._real, name)

            @contextmanager
            def flaky_connect(**kwargs):
                with original_connect(**kwargs) as real_conn:
                    yield _CrashAfterFirstDependentUpdate(real_conn)

            with patch.object(db_mod, "connect", flaky_connect):
                with pytest.raises(RuntimeError, match="simulated crash"):
                    db_mod.complete_feature_and_cascade(feat_a.id)

            # The atomic invariant: A is still 'ready' (its 'completed'
            # write was rolled back), AND BOTH dependents are still
            # 'pending'. The dependent whose UPDATE *did* execute on
            # the live connection must have been rolled back along with
            # the rest of the transaction; otherwise we'd have a
            # partial cascade — exactly the bug this helper exists to
            # prevent.
            assert get_feature(feat_a.id).status == "ready"
            assert get_feature(feat_b.id).status == "pending", (
                "feat_b must be pending after rollback (rollback failed "
                "to undo the first dependent UPDATE)"
            )
            assert get_feature(feat_c.id).status == "pending", (
                "feat_c must be pending after rollback"
            )

    def test_handle_execution_result_uses_atomic_helper(
        self, tmp_db, project, feature
    ):
        """handle_execution_result must call complete_feature_and_cascade
        rather than the two old separate calls. Verify by spying."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            result = ExecutionResult(
                text="OK", is_error=False, total_cost_usd=1.0
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            spawn_result = SpawnResult(
                execution_result=result, agent_run=agent_run
            )

            with patch(
                "bob3.orchestrator.run_loop.db.complete_feature_and_cascade",
                return_value=[],
            ) as spy:
                handle_execution_result(
                    project_id=project.id,
                    feature=feature,
                    spawn_result=spawn_result,
                )

            spy.assert_called_once_with(feature.id)


# ============================================================
# Recovery scan: orphaned 'pending' features get promoted
# ============================================================


class TestOrphanedPendingRecovery:
    """A crash between the legacy update_feature(...completed) and
    update_dependent_features_readiness(...) would leave dependents in
    'pending' even though their deps are all 'completed'. The new
    recovery scan in _resume_interrupted_work fixes that on startup.
    """

    def test_orphaned_pending_promoted_to_ready(self, tmp_db, project):
        """Set up a synthetic post-crash state and ensure the recovery
        scan promotes the dependent."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import add_feature_dependency

            # A is already completed; B depends on A but is still pending.
            # That's exactly what a crash between steps (1) and (2) leaves.
            feat_a = create_feature(
                project_id=project.id,
                name="A",
                description="upstream completed",
                status="completed",
                priority=10,
                risk_category="medium",
            )
            feat_b = create_feature(
                project_id=project.id,
                name="B",
                description="orphaned downstream",
                status="pending",
                priority=20,
                risk_category="medium",
            )
            update_feature(
                feat_b.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            add_feature_dependency(
                feature_id=feat_b.id, depends_on_feature_id=feat_a.id
            )

            loop = OrchestrationLoop(project_id=project.id)
            loop._resume_interrupted_work()

            assert get_feature(feat_b.id).status == "ready"

    def test_orphan_recovery_leaves_legitimate_pending_alone(
        self, tmp_db, project
    ):
        """Don't promote pending features whose deps are NOT all completed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import add_feature_dependency

            feat_a = create_feature(
                project_id=project.id,
                name="A",
                description="still in progress",
                status="executing",
                priority=10,
                risk_category="medium",
            )
            feat_b = create_feature(
                project_id=project.id,
                name="B",
                description="legitimately pending",
                status="pending",
                priority=20,
                risk_category="medium",
            )
            add_feature_dependency(
                feature_id=feat_b.id, depends_on_feature_id=feat_a.id
            )

            loop = OrchestrationLoop(project_id=project.id)
            loop._resume_interrupted_work()

            # B must still be pending; A is unfinished, so the orphan
            # scan rule (all deps completed) doesn't apply.
            assert get_feature(feat_b.id).status == "pending"

    def test_orphan_recovery_runs_even_with_no_stale_features(
        self, tmp_db, project
    ):
        """Empty 'executing'/'interrupted' lists must not skip the orphan
        scan — that early-return was the original bug shape."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import add_feature_dependency

            feat_a = create_feature(
                project_id=project.id,
                name="A",
                description="upstream completed",
                status="completed",
                priority=10,
                risk_category="medium",
            )
            feat_b = create_feature(
                project_id=project.id,
                name="B",
                description="orphan",
                status="pending",
                priority=20,
                risk_category="medium",
            )
            add_feature_dependency(
                feature_id=feat_b.id, depends_on_feature_id=feat_a.id
            )

            # No 'executing' or 'interrupted' features in the project.
            loop = OrchestrationLoop(project_id=project.id)
            loop._resume_interrupted_work()

            assert get_feature(feat_b.id).status == "ready"


# ============================================================
# Git hook failure handling at the run_loop call site
# ============================================================


def _make_git_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Initialize a git repo with one initial commit and return the path."""
    repo = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=str(repo), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo), capture_output=True, check=True,
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(
        ["git", "add", "."], cwd=str(repo), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo), capture_output=True, check=True,
    )
    return repo


def _install_rejecting_pre_commit_hook(repo: pathlib.Path) -> None:
    """Install a pre-commit hook that always rejects with a clear message."""
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-commit"
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'pre-commit hook failed: forbidden token detected' >&2\n"
        "exit 1\n"
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class TestGitHookFailureHandling:
    """A pre-commit hook rejection should mark the feature needs_human and
    record evidence — not silently mark it completed."""

    @pytest.fixture
    def workspace(self, tmp_path):
        return _make_git_workspace(tmp_path)

    @pytest.fixture
    def workspace_project(self, tmp_db, workspace):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            return create_project(
                name="hook-test",
                workspace_path=str(workspace),
                max_cost_usd=100.0,
            )

    @pytest.fixture
    def workspace_feature(self, tmp_db, workspace_project, workspace):
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            f = create_feature(
                project_id=workspace_project.id,
                name="Feature blocked by hook",
                description="A feature that will trip a pre-commit hook",
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
            # Drop a real change inside the workspace so `git add -A` finds
            # something to stage.
            (workspace / "code.py").write_text("# implementation\n")
            return get_feature(f.id)

    @pytest.mark.asyncio
    async def test_hook_failure_marks_feature_needs_human(
        self, tmp_db, workspace_project, workspace_feature, workspace
    ):
        """A pre-commit hook rejecting the commit should flip the feature
        status to needs_human after handle_execution_result has already
        marked it completed."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            _install_rejecting_pre_commit_hook(workspace)

            loop = OrchestrationLoop(
                project_id=workspace_project.id,
                workspace=str(workspace),
            )

            mock_result = ExecutionResult(
                text="Implemented and verified",
                is_error=False,
                duration_ms=1000,
                num_turns=3,
                total_cost_usd=0.10,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            # Patch verification to pass so we reach the commit path.
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={"passed": True, "summary": "ok", "checks": []},
            ):
                await loop.execute_feature(workspace_feature)

            # Feature should be needs_human, NOT completed.
            updated = get_feature(workspace_feature.id)
            assert updated.status == "needs_human", (
                f"Expected needs_human after hook rejection, got {updated.status}"
            )

            # Loop counters should reflect failure rather than completion.
            assert loop.features_completed == 0
            assert loop.features_failed == 1

    @pytest.mark.asyncio
    async def test_hook_failure_creates_git_hook_failure_evidence(
        self, tmp_db, workspace_project, workspace_feature, workspace
    ):
        """Hook output must be captured as evidence for human review."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            _install_rejecting_pre_commit_hook(workspace)

            loop = OrchestrationLoop(
                project_id=workspace_project.id,
                workspace=str(workspace),
            )

            mock_result = ExecutionResult(
                text="Done",
                is_error=False,
                duration_ms=1000,
                num_turns=2,
                total_cost_usd=0.10,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={"passed": True, "summary": "ok", "checks": []},
            ):
                await loop.execute_feature(workspace_feature)

            evidence_list = query_evidence(
                project_id=workspace_project.id,
                feature_id=workspace_feature.id,
            )
            hook_evidence = [
                e for e in evidence_list if e.type == "git_hook_failure"
            ]
            assert len(hook_evidence) == 1, (
                f"Expected one git_hook_failure evidence, got "
                f"{len(hook_evidence)} (all types: {[e.type for e in evidence_list]})"
            )
            payload = json.loads(hook_evidence[0].content)
            assert payload["feature_id"] == workspace_feature.id
            assert payload["returncode"] != 0
            combined = (payload.get("stderr") or "") + (payload.get("stdout") or "")
            assert "forbidden token detected" in combined

    @pytest.mark.asyncio
    async def test_hook_failure_does_not_cascade_dependents(
        self, tmp_db, workspace_project, workspace_feature, workspace
    ):
        """A hook-blocked feature must NOT unlock dependent features."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Create a dependent feature B that depends on the hook-blocked A.
            feat_b = create_feature(
                project_id=workspace_project.id,
                name="Dependent feature",
                description="Depends on A",
                status="pending",
                priority=20,
                risk_category="medium",
            )
            update_feature(
                feat_b.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            add_feature_dependency(
                feature_id=feat_b.id,
                depends_on_feature_id=workspace_feature.id,
            )

            _install_rejecting_pre_commit_hook(workspace)

            loop = OrchestrationLoop(
                project_id=workspace_project.id,
                workspace=str(workspace),
            )

            mock_result = ExecutionResult(
                text="Done",
                is_error=False,
                duration_ms=1000,
                num_turns=2,
                total_cost_usd=0.10,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={"passed": True, "summary": "ok", "checks": []},
            ):
                await loop.execute_feature(workspace_feature)

            # Dependent must still be pending — it must not have been
            # cascaded to 'ready' on a hook-blocked parent.
            dep_after = get_feature(feat_b.id)
            assert dep_after.status == "pending", (
                f"Dependent should remain pending after hook failure, got "
                f"{dep_after.status}"
            )

    @pytest.mark.asyncio
    async def test_clean_repo_skip_does_not_mark_needs_human(
        self, tmp_db, workspace_project, workspace_feature, workspace
    ):
        """If the workspace simply has nothing to commit, the feature should
        remain 'completed' — only an actual hook rejection triggers
        needs_human."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Remove the staged change so `git diff --cached` is clean and
            # `commit_feature` returns None without raising.
            (workspace / "code.py").unlink(missing_ok=True)

            loop = OrchestrationLoop(
                project_id=workspace_project.id,
                workspace=str(workspace),
            )

            mock_result = ExecutionResult(
                text="Done",
                is_error=False,
                duration_ms=1000,
                num_turns=2,
                total_cost_usd=0.10,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={"passed": True, "summary": "ok", "checks": []},
            ):
                await loop.execute_feature(workspace_feature)

            updated = get_feature(workspace_feature.id)
            assert updated.status == "completed"
            assert loop.features_completed == 1
            assert loop.features_failed == 0


# ============================================================
# Atomicity: rollback_feature_cascade rolls back as a single transaction
# (regression test for R4-003 — analog of R2-009 but on the rollback path)
# ============================================================


class TestRollbackFeatureCascadeAtomicity:
    """When a git hook rejection forces a previously-cascaded feature back to
    ``needs_human``, the rollback of the feature status AND the dependent-
    cascade revert must happen atomically. A multi-step Python loop calling
    update_feature per dependent leaves a partial-state window: a crash
    mid-loop strands some dependents at 'ready' and others at 'pending'.
    """

    def _make_diamond_top(self, project):
        """Set up A → B and A → C, with A 'completed' and B+C 'ready'."""
        from bob3.db import add_feature_dependency

        feat_a = create_feature(
            project_id=project.id,
            name="A",
            description="upstream",
            status="completed",
            priority=10,
            risk_category="medium",
        )
        feat_b = create_feature(
            project_id=project.id,
            name="B",
            description="downstream-1",
            status="ready",
            priority=20,
            risk_category="medium",
        )
        feat_c = create_feature(
            project_id=project.id,
            name="C",
            description="downstream-2",
            status="ready",
            priority=20,
            risk_category="medium",
        )
        add_feature_dependency(
            feature_id=feat_b.id, depends_on_feature_id=feat_a.id
        )
        add_feature_dependency(
            feature_id=feat_c.id, depends_on_feature_id=feat_a.id
        )
        return (
            get_feature(feat_a.id),
            get_feature(feat_b.id),
            get_feature(feat_c.id),
        )

    def test_happy_path_reverts_feature_and_all_dependents(
        self, tmp_db, project
    ):
        """Sanity: the atomic helper resets A to needs_human and flips
        every ready dependent back to pending."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import rollback_feature_cascade

            feat_a, feat_b, feat_c = self._make_diamond_top(project)
            reverted = rollback_feature_cascade(
                feat_a.id, target_status="needs_human"
            )

            assert get_feature(feat_a.id).status == "needs_human"
            assert get_feature(feat_b.id).status == "pending"
            assert get_feature(feat_c.id).status == "pending"
            assert sorted(reverted) == sorted([feat_b.id, feat_c.id])

    def test_rollback_is_atomic_no_partial_state_on_crash(
        self, tmp_db, project
    ):
        """The load-bearing invariant: if any SQL inside the rollback raises,
        the whole transaction rolls back. A and B and C all stay where they
        were before the rollback call. We never see a partial-state world
        where, say, B was reset but C wasn't.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            import bob3.db as db_mod

            feat_a, feat_b, feat_c = self._make_diamond_top(project)

            # Wrap the connection so its second execute() raises. The first
            # execute is the feature-status UPDATE; the second is the
            # dependent-revert UPDATE. By failing the second call we simulate
            # a crash AFTER the feature row is touched but BEFORE the
            # dependents are updated. With proper atomicity, the outer
            # context manager rolls back BOTH.
            original_connect = db_mod.connect

            from contextlib import contextmanager

            class _FlakyConn:
                def __init__(self, real_conn):
                    self._real = real_conn
                    self._calls = 0

                def execute(self, sql, *a, **kw):
                    self._calls += 1
                    if self._calls == 2:
                        raise RuntimeError("simulated crash mid-rollback")
                    return self._real.execute(sql, *a, **kw)

                def __getattr__(self, name):
                    return getattr(self._real, name)

            @contextmanager
            def flaky_connect(**kwargs):
                with original_connect(**kwargs) as real_conn:
                    yield _FlakyConn(real_conn)

            with patch.object(db_mod, "connect", flaky_connect):
                with pytest.raises(RuntimeError, match="simulated crash"):
                    db_mod.rollback_feature_cascade(
                        feat_a.id, target_status="needs_human"
                    )

            # Atomic invariant: nothing changed. A is still 'completed' (the
            # state before rollback), and BOTH dependents are still 'ready'.
            # No half-rolled-back state with B 'pending' but C 'ready'.
            assert get_feature(feat_a.id).status == "completed"
            assert get_feature(feat_b.id).status == "ready"
            assert get_feature(feat_c.id).status == "ready"

    def test_target_status_is_applied_to_feature(self, tmp_db, project):
        """A.status must equal the requested target_status after a
        successful rollback (here: needs_human)."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import rollback_feature_cascade

            feat_a, feat_b, feat_c = self._make_diamond_top(project)
            rollback_feature_cascade(feat_a.id, target_status="needs_human")
            assert get_feature(feat_a.id).status == "needs_human"

    def test_dependents_in_non_ready_states_are_left_alone(
        self, tmp_db, project
    ):
        """If a dependent has already advanced past 'ready' (e.g. it is
        currently 'in_progress' or even 'completed'), the rollback must not
        flip it back to 'pending' — that would corrupt running/finished
        work. Only 'ready' dependents are reverted."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            from bob3.db import rollback_feature_cascade

            feat_a, feat_b, feat_c = self._make_diamond_top(project)
            # Advance C to 'in_progress' to simulate a worker having
            # already picked it up before we discovered A's hook failure.
            update_feature(feat_c.id, status="in_progress")

            rollback_feature_cascade(feat_a.id, target_status="needs_human")

            assert get_feature(feat_a.id).status == "needs_human"
            assert get_feature(feat_b.id).status == "pending"
            # C must NOT be reverted; it's already running.
            assert get_feature(feat_c.id).status == "in_progress"

    @pytest.mark.asyncio
    async def test_execute_feature_uses_atomic_rollback_on_hook_failure(
        self, tmp_db
    ):
        """End-to-end: on a git hook rejection in execute_feature, the
        rollback must go through the new atomic db.rollback_feature_cascade
        rather than the old multi-step update_feature loop."""
        from bob3.db import add_feature_dependency

        with patch("bob3.db.get_database_path", return_value=tmp_db):
            workspace = _make_git_workspace(pathlib.Path(tmp_db).parent)
            proj = create_project(
                name="atomic-rollback",
                workspace_path=str(workspace),
                max_cost_usd=100.0,
            )
            feat_a = create_feature(
                project_id=proj.id,
                name="A",
                description="will be hook-blocked",
                status="ready",
                priority=10,
                risk_category="medium",
            )
            update_feature(
                feat_a.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            feat_b = create_feature(
                project_id=proj.id,
                name="B",
                description="downstream",
                status="pending",
                priority=20,
                risk_category="medium",
            )
            add_feature_dependency(
                feature_id=feat_b.id, depends_on_feature_id=feat_a.id,
            )
            (workspace / "code.py").write_text("# implementation\n")
            _install_rejecting_pre_commit_hook(workspace)

            mock_result = ExecutionResult(
                text="Done", is_error=False, duration_ms=1000,
                num_turns=2, total_cost_usd=0.10,
            )
            mock_agent_run = MagicMock()
            mock_agent_run.id = str(uuid.uuid4())

            loop = OrchestrationLoop(
                project_id=proj.id, workspace=str(workspace),
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    execution_result=mock_result, agent_run=mock_agent_run,
                ),
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={"passed": True, "summary": "ok", "checks": []},
            ), patch(
                "bob3.orchestrator.run_loop.db.rollback_feature_cascade",
                wraps=__import__("bob3").db.rollback_feature_cascade,
            ) as spy:
                feat_a_obj = get_feature(feat_a.id)
                await loop.execute_feature(feat_a_obj)

                # The atomic helper must have been called exactly once with
                # the hook-blocked feature and the needs_human target.
                assert spy.call_count == 1
                args, kwargs = spy.call_args
                assert (args and args[0] == feat_a.id) or (
                    kwargs.get("feature_id") == feat_a.id
                )
                assert kwargs.get("target_status") == "needs_human"

            # And the end state matches: A=needs_human, B=pending. No
            # partial state.
            assert get_feature(feat_a.id).status == "needs_human"
            assert get_feature(feat_b.id).status == "pending"
