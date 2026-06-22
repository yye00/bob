"""Tests for F020: Database operations for sub_agent_runs table."""

import json
import os
import pathlib
import tempfile

import pytest

from bob3 import db
from bob3.models import SubAgentRun


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project for agent run operations."""
    return db.create_project(
        name="Test Project",
        workspace_path="/tmp/test-project",
    )


# ============================================================
# Step 1: create_agent_run()
# ============================================================


class TestCreateAgentRun:
    """Tests for create_agent_run() function."""

    def test_create_minimal(self, project):
        """Create an agent run with only required fields."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        assert isinstance(run, SubAgentRun)
        assert run.id is not None
        assert run.project_id == project.id
        assert run.purpose == "implement_feature"
        assert run.status == "running"
        assert run.created_at is not None
        assert run.completed_at is None

    def test_create_with_all_fields(self, project):
        """Create an agent run with all optional fields populated."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            target_type="feature",
            target_id="F001",
            prompt_summary="Analyze test failure in feature F001",
            mcp_enabled=json.dumps(["perplexity", "puppeteer"]),
        )

        assert run.purpose == "rca_analyst"
        assert run.target_type == "feature"
        assert run.target_id == "F001"
        assert run.prompt_summary == "Analyze test failure in feature F001"
        assert run.mcp_enabled == json.dumps(["perplexity", "puppeteer"])

    def test_create_with_parent_run(self, project):
        """Create a child agent run linked to a parent."""
        parent = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        child = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=parent.id,
        )

        assert child.parent_run_id == parent.id

    def test_create_with_custom_id(self, project):
        """Create an agent run with a custom ID."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="test_run",
            run_id="custom-run-id-123",
        )

        assert run.id == "custom-run-id-123"

    def test_create_persists_to_database(self, project):
        """Verify created agent run can be retrieved from database."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        retrieved = db.get_agent_run(run.id)
        assert retrieved is not None
        assert retrieved.id == run.id
        assert retrieved.project_id == project.id
        assert retrieved.purpose == "implement_feature"


# ============================================================
# Step 2: update_agent_run()
# ============================================================


class TestUpdateAgentRun:
    """Tests for update_agent_run() function."""

    def test_update_status(self, project):
        """Update agent run status."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(run.id, status="completed")
        assert updated is not None
        assert updated.status == "completed"

    def test_update_result_summary(self, project):
        """Update agent run with result summary."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            result_summary="Successfully implemented feature with 5 tests passing",
        )
        assert updated is not None
        assert updated.result_summary == "Successfully implemented feature with 5 tests passing"

    def test_update_rca_fields(self, project):
        """Update RCA-specific fields."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
        )

        updated = db.update_agent_run(
            run.id,
            rca_blame_target="implementation",
            rca_recommended_action="fix_bug",
        )
        assert updated is not None
        assert updated.rca_blame_target == "implementation"
        assert updated.rca_recommended_action == "fix_bug"

    def test_update_cost_and_tokens(self, project):
        """Update cost and token tracking fields."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            tokens_in=5000,
            tokens_out=3000,
            cost_usd=0.15,
            duration_ms=45000,
        )
        assert updated is not None
        assert updated.tokens_in == 5000
        assert updated.tokens_out == 3000
        assert updated.cost_usd == pytest.approx(0.15)
        assert updated.duration_ms == 45000

    def test_update_completed_at(self, project):
        """Update completed_at timestamp."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            status="completed",
            completed_at="2026-02-19T12:00:00",
        )
        assert updated is not None
        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_update_nonexistent_returns_none(self, project):
        """Update of nonexistent agent run returns None."""
        result = db.update_agent_run("nonexistent-id", status="completed")
        assert result is None

    def test_update_multiple_fields(self, project):
        """Update multiple fields at once."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            status="completed",
            result_summary="Done",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=0.05,
            duration_ms=30000,
            evidence_artifacts_produced=json.dumps(["ev-001", "ev-002"]),
            improvement_type="implementation",
            improvement_evidence="All tests passing",
        )
        assert updated is not None
        assert updated.status == "completed"
        assert updated.result_summary == "Done"
        assert updated.tokens_in == 1000
        assert updated.improvement_type == "implementation"


# ============================================================
# Step 3: get_agent_run()
# ============================================================


class TestGetAgentRun:
    """Tests for get_agent_run() function."""

    def test_get_existing(self, project):
        """Get an existing agent run by ID."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            target_type="feature",
            target_id="F001",
        )

        retrieved = db.get_agent_run(run.id)
        assert retrieved is not None
        assert retrieved.id == run.id
        assert retrieved.project_id == project.id
        assert retrieved.purpose == "implement_feature"
        assert retrieved.target_type == "feature"
        assert retrieved.target_id == "F001"

    def test_get_nonexistent_returns_none(self, project):
        """Get of nonexistent agent run returns None."""
        result = db.get_agent_run("nonexistent-id")
        assert result is None

    def test_get_returns_correct_model_type(self, project):
        """Returned object is a SubAgentRun model instance."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        retrieved = db.get_agent_run(run.id)
        assert isinstance(retrieved, SubAgentRun)


# ============================================================
# Step 4: query_agent_runs() with filtering
# ============================================================


class TestQueryAgentRuns:
    """Tests for query_agent_runs() with filtering."""

    def test_query_by_project_id(self, project):
        """Query runs filtered by project_id."""
        db.create_agent_run(project_id=project.id, purpose="run1")
        db.create_agent_run(project_id=project.id, purpose="run2")

        other_proj = db.create_project(name="Other", workspace_path="/tmp/other")
        db.create_agent_run(project_id=other_proj.id, purpose="run3")

        runs = db.query_agent_runs(project_id=project.id)
        assert len(runs) == 2
        assert all(r.project_id == project.id for r in runs)

    def test_query_by_status(self, project):
        """Query runs filtered by status."""
        run1 = db.create_agent_run(project_id=project.id, purpose="run1")
        run2 = db.create_agent_run(project_id=project.id, purpose="run2")
        db.update_agent_run(run1.id, status="completed")

        running = db.query_agent_runs(project_id=project.id, status="running")
        assert len(running) == 1
        assert running[0].id == run2.id

        completed = db.query_agent_runs(project_id=project.id, status="completed")
        assert len(completed) == 1
        assert completed[0].id == run1.id

    def test_query_by_purpose(self, project):
        """Query runs filtered by purpose."""
        db.create_agent_run(project_id=project.id, purpose="implement_feature")
        db.create_agent_run(project_id=project.id, purpose="rca_analyst")
        db.create_agent_run(project_id=project.id, purpose="implement_feature")

        runs = db.query_agent_runs(project_id=project.id, purpose="implement_feature")
        assert len(runs) == 2
        assert all(r.purpose == "implement_feature" for r in runs)

    def test_query_by_parent_run_id(self, project):
        """Query child runs by parent_run_id."""
        parent = db.create_agent_run(project_id=project.id, purpose="orchestrator")
        db.create_agent_run(
            project_id=project.id, purpose="child1", parent_run_id=parent.id
        )
        db.create_agent_run(
            project_id=project.id, purpose="child2", parent_run_id=parent.id
        )
        db.create_agent_run(project_id=project.id, purpose="orphan")

        children = db.query_agent_runs(project_id=project.id, parent_run_id=parent.id)
        assert len(children) == 2

    def test_query_combined_filters(self, project):
        """Query with multiple filter criteria."""
        parent = db.create_agent_run(project_id=project.id, purpose="orchestrator")
        child1 = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=parent.id,
        )
        child2 = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=parent.id,
        )
        db.update_agent_run(child1.id, status="completed")

        runs = db.query_agent_runs(
            project_id=project.id,
            purpose="implement_feature",
            status="running",
            parent_run_id=parent.id,
        )
        assert len(runs) == 1
        assert runs[0].id == child2.id

    def test_query_ordered_by_created_at(self, project):
        """Results are ordered by created_at ascending."""
        run1 = db.create_agent_run(project_id=project.id, purpose="first")
        run2 = db.create_agent_run(project_id=project.id, purpose="second")
        run3 = db.create_agent_run(project_id=project.id, purpose="third")

        runs = db.query_agent_runs(project_id=project.id)
        assert runs[0].id == run1.id
        assert runs[1].id == run2.id
        assert runs[2].id == run3.id

    def test_query_requires_project_id(self, project):
        """query_agent_runs requires project_id."""
        with pytest.raises(ValueError):
            db.query_agent_runs()

    def test_query_empty_results(self, project):
        """Query with no matching results returns empty list."""
        runs = db.query_agent_runs(project_id=project.id, purpose="nonexistent")
        assert runs == []


# ============================================================
# Step 5: Agent run tracking integration
# ============================================================


class TestAgentRunTracking:
    """Integration tests for agent run tracking workflow."""

    def test_full_lifecycle(self, project):
        """Test complete agent run lifecycle: create -> update -> complete."""
        # Create
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            target_type="feature",
            target_id="F001",
            prompt_summary="Implement database schema for feature F001",
        )
        assert run.status == "running"

        # Update during execution
        db.update_agent_run(
            run.id,
            tokens_in=2500,
            tokens_out=1500,
        )

        # Complete
        updated = db.update_agent_run(
            run.id,
            status="completed",
            result_summary="Feature implemented with 3 files, all tests passing",
            tokens_in=5000,
            tokens_out=3000,
            cost_usd=0.15,
            duration_ms=120000,
            completed_at="2026-02-19T12:00:00",
        )

        assert updated.status == "completed"
        assert updated.tokens_in == 5000
        assert updated.tokens_out == 3000
        assert updated.cost_usd == pytest.approx(0.15)
        assert updated.duration_ms == 120000

    def test_parent_child_hierarchy(self, project):
        """Test parent-child agent run hierarchy."""
        parent = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )

        child1 = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=parent.id,
        )

        child2 = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            parent_run_id=parent.id,
        )

        # Query children
        children = db.query_agent_runs(
            project_id=project.id,
            parent_run_id=parent.id,
        )
        assert len(children) == 2
        assert {c.id for c in children} == {child1.id, child2.id}

    def test_failed_run(self, project):
        """Test tracking a failed agent run."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            status="failed",
            result_summary="Failed: unable to resolve dependency conflict",
            cost_usd=0.05,
            duration_ms=30000,
        )

        assert updated.status == "failed"
        assert "Failed" in updated.result_summary


# ============================================================
# Step 6: Cost and token tracking
# ============================================================


class TestCostAndTokenTracking:
    """Tests for cost and token tracking in agent runs."""

    def test_token_tracking(self, project):
        """Track input and output token counts."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            tokens_in=10000,
            tokens_out=8000,
        )

        assert updated.tokens_in == 10000
        assert updated.tokens_out == 8000

    def test_cost_tracking(self, project):
        """Track USD cost of agent run."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            cost_usd=1.25,
        )

        assert updated.cost_usd == pytest.approx(1.25)

    def test_duration_tracking(self, project):
        """Track duration in milliseconds."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            duration_ms=300000,
        )

        assert updated.duration_ms == 300000

    def test_zero_cost_run(self, project):
        """Handle a run with zero cost."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
        )

        updated = db.update_agent_run(
            run.id,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            duration_ms=0,
        )

        assert updated.tokens_in == 0
        assert updated.cost_usd == pytest.approx(0.0)

    def test_mcp_enabled_tracking(self, project):
        """Track which MCP plugins were enabled."""
        run = db.create_agent_run(
            project_id=project.id,
            purpose="research",
            mcp_enabled=json.dumps(["perplexity"]),
        )

        retrieved = db.get_agent_run(run.id)
        assert retrieved is not None
        mcp_list = json.loads(retrieved.mcp_enabled)
        assert "perplexity" in mcp_list


# ============================================================
# count_agent_runs() perf test
# ============================================================


class TestCountAgentRuns:
    """Tests for count_agent_runs() - SQL COUNT(*) for fast filtering."""

    def test_count_matches_python_count_and_is_fast(self, project):
        """Count via SQL matches Python-side count and runs in < 100ms."""
        import time

        # Create ~100 agent runs across multiple feature_ids and statuses.
        feature_ids = ["F100", "F101", "F102", "F103"]
        statuses = ["running", "completed", "failed"]
        purposes = ["implement_feature", "rca_analyst"]

        created: list[tuple[str, str, str, str]] = []  # (id, target_id, purpose, status)
        i = 0
        for f_idx, fid in enumerate(feature_ids):
            for s_idx, st in enumerate(statuses):
                for p_idx, pp in enumerate(purposes):
                    # Repeat a few times so we land near 100 rows.
                    for _ in range(4 + (i % 3)):
                        run = db.create_agent_run(
                            project_id=project.id,
                            purpose=pp,
                            target_type="feature",
                            target_id=fid,
                        )
                        # Move out of default 'running' when needed.
                        if st != "running":
                            db.update_agent_run(run.id, status=st)
                        created.append((run.id, fid, pp, st))
                        i += 1

        assert len(created) >= 100, f"expected ~100 rows, got {len(created)}"

        target_fid = "F101"
        target_purpose = "implement_feature"
        target_status = "failed"

        # Python-side reference count using query_agent_runs.
        all_runs = db.query_agent_runs(project_id=project.id, purpose=target_purpose)
        expected = sum(
            1
            for r in all_runs
            if r.target_id == target_fid and r.status == target_status
        )

        # Sanity: should be > 0 given how we constructed the dataset.
        assert expected > 0

        start = time.perf_counter()
        actual = db.count_agent_runs(
            project_id=project.id,
            target_id=target_fid,
            purpose=target_purpose,
            status=target_status,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert actual == expected, f"count mismatch: sql={actual}, python={expected}"
        assert elapsed_ms < 100.0, f"count_agent_runs too slow: {elapsed_ms:.1f}ms"

    def test_count_no_filters_returns_all_for_project(self, project):
        """With only project_id, count returns all runs for that project."""
        for _ in range(5):
            db.create_agent_run(project_id=project.id, purpose="implement_feature")

        other = db.create_project(name="Other", workspace_path="/tmp/other-cnt")
        db.create_agent_run(project_id=other.id, purpose="implement_feature")

        assert db.count_agent_runs(project_id=project.id) == 5
        assert db.count_agent_runs(project_id=other.id) == 1

    def test_count_zero_when_no_match(self, project):
        """Returns 0 when no rows match the filters."""
        db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            target_type="feature",
            target_id="F001",
        )
        assert (
            db.count_agent_runs(
                project_id=project.id,
                target_id="F999",
                purpose="implement_feature",
                status="failed",
            )
            == 0
        )
