"""Tests for F054: Implement resource cost tracking and limit enforcement."""

import pathlib

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project with a known max_cost_usd."""
    from bob3.db import create_project

    return create_project(
        name="Cost Tracking Test",
        workspace_path="/tmp/cost-test",
        max_cost_usd=100.0,
    )


# ============================================================
# Step 1: Add update_project_cost() function
# ============================================================


class TestUpdateProjectCostExists:
    """Step 1: update_project_cost() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob3.db import update_project_cost

        assert callable(update_project_cost)

    def test_returns_project_model(self, project):
        from bob3.db import update_project_cost
        from bob3.models import Project

        result = update_project_cost(project_id=project.id, cost_usd=5.0)
        assert isinstance(result, Project)


# ============================================================
# Step 2: Increment total_cost_usd on each agent run
# ============================================================


class TestIncrementTotalCostUsd:
    """Step 2: total_cost_usd is incremented by the given amount."""

    def test_single_cost_increment(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=10.0)
        assert result.total_cost_usd == 10.0

    def test_multiple_cost_increments_accumulate(self, project):
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=10.0)
        update_project_cost(project_id=project.id, cost_usd=25.0)
        result = update_project_cost(project_id=project.id, cost_usd=5.0)
        assert result.total_cost_usd == 40.0

    def test_zero_cost_leaves_total_unchanged(self, project):
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=20.0)
        result = update_project_cost(project_id=project.id, cost_usd=0.0)
        assert result.total_cost_usd == 20.0

    def test_cost_persisted_in_database(self, project):
        from bob3.db import get_project, update_project_cost

        update_project_cost(project_id=project.id, cost_usd=42.5)
        fetched = get_project(project.id)
        assert fetched is not None
        assert fetched.total_cost_usd == 42.5

    def test_nonexistent_project_returns_none(self, db_path):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id="nonexistent-id", cost_usd=10.0)
        assert result is None


# ============================================================
# Step 3: Check against max_cost_usd
# ============================================================


class TestCheckAgainstMaxCost:
    """Step 3: update_project_cost checks total against max_cost_usd."""

    def test_under_limit_status_unchanged(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=50.0)
        assert result.status == "planning"  # Original status preserved

    def test_at_exact_limit_no_trigger(self, project):
        """Exactly at the limit should NOT trigger resource_limited."""
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=100.0)
        assert result.status == "planning"

    def test_over_limit_detected(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=101.0)
        assert result.total_cost_usd == 101.0
        assert result.status == "resource_limited"


# ============================================================
# Step 4: Set project status to 'resource_limited' if exceeded
# ============================================================


class TestResourceLimitedStatus:
    """Step 4: Project status changes to 'resource_limited' when cost exceeds limit."""

    def test_status_set_to_resource_limited(self, project):
        from bob3.db import update_project_cost

        result = update_project_cost(project_id=project.id, cost_usd=110.0)
        assert result.status == "resource_limited"

    def test_resource_limited_persisted(self, project):
        from bob3.db import get_project, update_project_cost

        update_project_cost(project_id=project.id, cost_usd=110.0)
        fetched = get_project(project.id)
        assert fetched is not None
        assert fetched.status == "resource_limited"
        assert fetched.total_cost_usd == 110.0

    def test_incremental_cost_triggers_limit(self, project):
        """Multiple small increments that cross the limit should trigger."""
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=50.0)
        update_project_cost(project_id=project.id, cost_usd=40.0)
        # Now at 90, still under 100
        result = update_project_cost(project_id=project.id, cost_usd=11.0)
        # Now at 101, over 100
        assert result.total_cost_usd == 101.0
        assert result.status == "resource_limited"

    def test_already_resource_limited_stays_limited(self, project):
        """Once resource_limited, additional costs keep the status."""
        from bob3.db import update_project_cost

        update_project_cost(project_id=project.id, cost_usd=110.0)
        result = update_project_cost(project_id=project.id, cost_usd=5.0)
        assert result.total_cost_usd == 115.0
        assert result.status == "resource_limited"


# ============================================================
# Step 5: Test: Set max_cost=100, add costs to 110, verify limit triggered
# ============================================================


class TestEndToEndCostLimitEnforcement:
    """Step 5: Full end-to-end test with max_cost=100 and total reaching 110."""

    def test_set_max_100_add_to_110_verify_limited(self, db_path):
        """E2E: Create project with max=100, add costs totaling 110, verify resource_limited."""
        from bob3.db import create_project, get_project, update_project_cost

        # Create project with max_cost_usd=100
        proj = create_project(
            name="E2E Cost Test",
            workspace_path="/tmp/e2e-cost",
            max_cost_usd=100.0,
        )
        assert proj.max_cost_usd == 100.0
        assert proj.total_cost_usd == 0.0

        # Simulate several agent runs adding cost
        update_project_cost(project_id=proj.id, cost_usd=30.0)
        update_project_cost(project_id=proj.id, cost_usd=30.0)
        update_project_cost(project_id=proj.id, cost_usd=30.0)

        # Check: at 90, still under limit
        check = get_project(proj.id)
        assert check is not None
        assert check.total_cost_usd == 90.0
        assert check.status == "planning"

        # Add 20 more -> total 110, over the 100 limit
        result = update_project_cost(project_id=proj.id, cost_usd=20.0)
        assert result.total_cost_usd == 110.0
        assert result.status == "resource_limited"

        # Verify in database
        final = get_project(proj.id)
        assert final is not None
        assert final.total_cost_usd == 110.0
        assert final.status == "resource_limited"

    def test_negative_cost_rejected(self, project):
        """Negative cost values should be rejected."""
        from bob3.db import update_project_cost

        with pytest.raises(ValueError, match="cost_usd must be non-negative"):
            update_project_cost(project_id=project.id, cost_usd=-5.0)
