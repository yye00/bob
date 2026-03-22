"""Tests for F096: End-to-end test - Feature decomposition (parent->children).

Exercises the complete decomposition lifecycle:
  Step 1: Create oversized feature (exceeds_size_limits=TRUE)
  Step 2: Trigger decomposition
  Step 3: Verify 3 child features created with parent_feature_id set
  Step 4: Verify decomposition_depth incremented
  Step 5: Verify child dependencies form DAG
  Step 6: Complete children in order
  Step 7: Verify parent marked complete when all children done
"""

import json
import pathlib
import tempfile

import pytest

from bob3 import db
from bob3.models import Feature


@pytest.fixture()
def tmp_db(monkeypatch):
    """Create a temporary database with schema initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test.db"
        monkeypatch.setattr(db, "get_database_path", lambda: db_path)
        db.init_database(db_path=db_path)
        yield db_path


# ============================================================
# Step 1: Create oversized feature (exceeds_size_limits=TRUE)
# ============================================================


class TestStep1CreateOversizedFeature:
    def test_create_feature_exceeding_size_limits(self, tmp_db):
        """Create a feature with size estimates that exceed limits."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Giant Monolith Feature",
            description="A feature far too large for a single implementation pass",
            acceptance_criteria=json.dumps([
                "Build database layer",
                "Build API endpoints",
                "Build frontend integration",
            ]),
            status="ready",
            priority=10,
            risk_category="medium",
        )
        # Set estimates that exceed size limits (>500 LOC, >5 files, >8 complexity)
        db.update_feature(
            feature.id,
            estimated_lines_of_code=1200,
            estimated_files_touched=12,
            estimated_complexity=9,
        )
        result = db.check_feature_size(feature.id)

        assert result is not None
        assert result["exceeds_size_limits"] is True
        assert len(result["violations"]) >= 1

        updated = db.get_feature(feature.id)
        assert updated.exceeds_size_limits is True
        assert updated.size_limit_justification is not None


# ============================================================
# Step 2: Trigger decomposition
# ============================================================


class TestStep2TriggerDecomposition:
    def test_decomposition_creates_children_and_sets_parent_status(self, tmp_db):
        """Decompose the oversized feature into child features."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Giant Monolith Feature",
            description="Too large",
            status="ready",
            priority=10,
        )
        db.update_feature(
            parent.id,
            estimated_lines_of_code=1200,
            estimated_files_touched=12,
            estimated_complexity=9,
        )
        db.check_feature_size(parent.id)

        # Manually create 3 child features (simulating decomposition result)
        child_specs = [
            {"name": "Database Schema Module", "priority": 10, "risk": "low"},
            {"name": "API Endpoints Module", "priority": 20, "risk": "medium"},
            {"name": "Frontend Integration Module", "priority": 30, "risk": "medium"},
        ]
        children = []
        for spec in child_specs:
            child = db.create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name=spec["name"],
                description=f"Child: {spec['name']}",
                status="ready",
                priority=spec["priority"],
                risk_category=spec["risk"],
            )
            children.append(child)

        # Set parent status to pending_decomposition
        db.update_feature(parent.id, status="pending_decomposition")

        updated_parent = db.get_feature(parent.id)
        assert updated_parent.status == "pending_decomposition"
        assert len(children) == 3


# ============================================================
# Step 3: Verify 3 child features created with parent_feature_id set
# ============================================================


class TestStep3VerifyChildFeatures:
    def test_children_have_correct_parent_id(self, tmp_db):
        """All 3 children reference the correct parent feature."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="pending_decomposition",
        )

        for i in range(3):
            db.create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name=f"Child {i + 1}",
                status="ready",
            )

        children = db.get_child_features(parent.id)
        assert len(children) == 3
        for child in children:
            assert child.parent_feature_id == parent.id
            assert child.project_id == project.id


# ============================================================
# Step 4: Verify decomposition_depth incremented
# ============================================================


class TestStep4DecompositionDepthIncremented:
    def test_children_have_depth_1(self, tmp_db):
        """Children of a root feature have decomposition_depth=1."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Root Feature",
            status="pending_decomposition",
        )
        assert parent.decomposition_depth == 0

        for i in range(3):
            child = db.create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name=f"Child {i + 1}",
            )
            assert child.decomposition_depth == 1

    def test_grandchildren_have_depth_2(self, tmp_db):
        """Grandchildren have decomposition_depth=2."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Root Feature",
        )
        child = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child Feature",
        )
        grandchild = db.create_child_feature(
            parent_feature_id=child.id,
            project_id=project.id,
            name="Grandchild Feature",
        )
        assert grandchild.decomposition_depth == 2


# ============================================================
# Step 5: Verify child dependencies form DAG
# ============================================================


class TestStep5ChildDependenciesFormDAG:
    def test_child_dependencies_are_dag(self, tmp_db):
        """Child feature dependencies form a valid DAG (no cycles)."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="pending_decomposition",
        )

        # Create 3 children with a linear dependency chain:
        # child_c depends on child_b, child_b depends on child_a
        child_a = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Database Schema",
            status="ready",
            priority=10,
        )
        child_b = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="API Endpoints",
            status="ready",
            priority=20,
        )
        child_c = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Frontend Integration",
            status="ready",
            priority=30,
        )

        # B depends on A, C depends on B
        db.add_feature_dependency(
            feature_id=child_b.id,
            depends_on_feature_id=child_a.id,
        )
        db.add_feature_dependency(
            feature_id=child_c.id,
            depends_on_feature_id=child_b.id,
        )

        # Validate dependencies form a DAG
        is_valid, cycle = db.validate_dependencies(project.id)
        assert is_valid is True
        assert cycle == []

        # Verify dependency relationships
        deps_b = db.get_feature_dependencies(child_b.id)
        assert len(deps_b) == 1
        assert deps_b[0].depends_on_feature_id == child_a.id

        deps_c = db.get_feature_dependencies(child_c.id)
        assert len(deps_c) == 1
        assert deps_c[0].depends_on_feature_id == child_b.id

        # child_a has no dependencies (it's the root of the chain)
        deps_a = db.get_feature_dependencies(child_a.id)
        assert len(deps_a) == 0


# ============================================================
# Step 6: Complete children in order
# ============================================================


class TestStep6CompleteChildrenInOrder:
    def test_complete_children_sequentially(self, tmp_db):
        """Complete children in dependency order: A -> B -> C."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="pending_decomposition",
        )

        child_a = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Database Schema",
            status="ready",
            priority=10,
        )
        child_b = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="API Endpoints",
            status="pending",
            priority=20,
        )
        child_c = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Frontend Integration",
            status="pending",
            priority=30,
        )

        db.add_feature_dependency(
            feature_id=child_b.id,
            depends_on_feature_id=child_a.id,
        )
        db.add_feature_dependency(
            feature_id=child_c.id,
            depends_on_feature_id=child_b.id,
        )

        # Complete child A
        db.update_feature(child_a.id, status="completed")
        a = db.get_feature(child_a.id)
        assert a.status == "completed"

        # Complete child B
        db.update_feature(child_b.id, status="completed")
        b = db.get_feature(child_b.id)
        assert b.status == "completed"

        # Complete child C
        db.update_feature(child_c.id, status="completed")
        c = db.get_feature(child_c.id)
        assert c.status == "completed"

        # All children are now completed
        children = db.get_child_features(parent.id)
        assert all(ch.status == "completed" for ch in children)


# ============================================================
# Step 7: Verify parent marked complete when all children done
# ============================================================


class TestStep7ParentMarkedComplete:
    def test_parent_auto_completes_when_all_children_done(self, tmp_db):
        """Parent transitions to 'completed' when all children are completed."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="pending_decomposition",
        )

        child_a = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child A",
            status="ready",
        )
        child_b = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child B",
            status="ready",
        )
        child_c = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child C",
            status="ready",
        )

        # Complete first two children — parent should NOT be completed yet
        db.update_feature(child_a.id, status="completed")
        result_a = db.check_parent_completion(child_a.id)
        assert result_a is False
        assert db.get_feature(parent.id).status == "pending_decomposition"

        db.update_feature(child_b.id, status="completed")
        result_b = db.check_parent_completion(child_b.id)
        assert result_b is False
        assert db.get_feature(parent.id).status == "pending_decomposition"

        # Complete last child — NOW parent should be completed
        db.update_feature(child_c.id, status="completed")
        result_c = db.check_parent_completion(child_c.id)
        assert result_c is True

        final_parent = db.get_feature(parent.id)
        assert final_parent.status == "completed"

    def test_parent_not_completed_if_child_still_pending(self, tmp_db):
        """Parent stays pending_decomposition if any child is not completed."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="pending_decomposition",
        )

        child_a = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child A",
            status="completed",
        )
        child_b = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child B",
            status="ready",  # Not completed
        )

        result = db.check_parent_completion(child_a.id)
        assert result is False
        assert db.get_feature(parent.id).status == "pending_decomposition"

    def test_no_parent_returns_false(self, tmp_db):
        """check_parent_completion returns False for features without a parent."""
        project = db.create_project(
            name="decomp-test-project",
            workspace_path="/tmp/decomp-ws",
        )
        feature = db.create_feature(
            project_id=project.id,
            name="Standalone Feature",
            status="completed",
        )
        result = db.check_parent_completion(feature.id)
        assert result is False


# ============================================================
# Full E2E: All 7 steps in a single test
# ============================================================


class TestFullDecompositionE2E:
    def test_complete_decomposition_lifecycle(self, tmp_db):
        """End-to-end: oversized feature -> decompose -> children -> complete -> parent done.

        Exercises the full acceptance criteria in a single sequential workflow:
          Step 1: Create oversized feature (exceeds_size_limits=TRUE)
          Step 2: Trigger decomposition
          Step 3: Verify 3 child features created with parent_feature_id set
          Step 4: Verify decomposition_depth incremented
          Step 5: Verify child dependencies form DAG
          Step 6: Complete children in order
          Step 7: Verify parent marked complete when all children done
        """
        # ---- Step 1: Create oversized feature ----
        project = db.create_project(
            name="e2e-decomp-project",
            workspace_path="/tmp/e2e-decomp-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Giant E2E Feature",
            description="A massive feature requiring decomposition",
            acceptance_criteria=json.dumps([
                "Database schema and migrations",
                "REST API endpoints",
                "Frontend integration with error handling",
            ]),
            status="ready",
            priority=10,
            risk_category="medium",
        )
        db.update_feature(
            parent.id,
            estimated_lines_of_code=1500,
            estimated_files_touched=15,
            estimated_complexity=10,
        )
        size_result = db.check_feature_size(parent.id)
        assert size_result["exceeds_size_limits"] is True

        refreshed_parent = db.get_feature(parent.id)
        assert refreshed_parent.exceeds_size_limits is True
        assert refreshed_parent.decomposition_depth == 0

        # ---- Step 2: Trigger decomposition (simulate agent result) ----
        child_specs = [
            {
                "name": "Database Schema Module",
                "description": "Schema definitions, migrations, connection pool",
                "priority": 10,
                "risk_category": "low",
            },
            {
                "name": "API Endpoints Module",
                "description": "REST endpoints for CRUD operations",
                "priority": 20,
                "risk_category": "medium",
            },
            {
                "name": "Frontend Integration Module",
                "description": "Connect frontend components to backend APIs",
                "priority": 30,
                "risk_category": "medium",
            },
        ]

        children = []
        for spec in child_specs:
            child = db.create_child_feature(
                parent_feature_id=parent.id,
                project_id=project.id,
                name=spec["name"],
                description=spec["description"],
                status="ready",
                priority=spec["priority"],
                risk_category=spec["risk_category"],
            )
            children.append(child)

        # Set parent to pending_decomposition
        db.update_feature(parent.id, status="pending_decomposition")
        assert db.get_feature(parent.id).status == "pending_decomposition"

        # ---- Step 3: Verify 3 child features with parent_feature_id ----
        db_children = db.get_child_features(parent.id)
        assert len(db_children) == 3
        for child in db_children:
            assert child.parent_feature_id == parent.id
            assert child.project_id == project.id
            assert isinstance(child, Feature)

        child_names = {c.name for c in db_children}
        assert "Database Schema Module" in child_names
        assert "API Endpoints Module" in child_names
        assert "Frontend Integration Module" in child_names

        # ---- Step 4: Verify decomposition_depth incremented ----
        for child in db_children:
            assert child.decomposition_depth == 1, (
                f"Child '{child.name}' should have depth 1, got {child.decomposition_depth}"
            )
        # Parent should still be at depth 0
        assert db.get_feature(parent.id).decomposition_depth == 0

        # ---- Step 5: Verify child dependencies form DAG ----
        # Sort children by priority to get deterministic order
        children_sorted = sorted(children, key=lambda c: c.priority)
        child_db = children_sorted[0]  # Database Schema (priority 10)
        child_api = children_sorted[1]  # API Endpoints (priority 20)
        child_fe = children_sorted[2]  # Frontend Integration (priority 30)

        # API depends on Database, Frontend depends on API
        db.add_feature_dependency(
            feature_id=child_api.id,
            depends_on_feature_id=child_db.id,
        )
        db.add_feature_dependency(
            feature_id=child_fe.id,
            depends_on_feature_id=child_api.id,
        )

        is_valid, cycle = db.validate_dependencies(project.id)
        assert is_valid is True, f"Dependencies contain cycle: {cycle}"
        assert cycle == []

        # Verify specific dependencies
        api_deps = db.get_feature_dependencies(child_api.id)
        assert any(d.depends_on_feature_id == child_db.id for d in api_deps)

        fe_deps = db.get_feature_dependencies(child_fe.id)
        assert any(d.depends_on_feature_id == child_api.id for d in fe_deps)

        db_deps = db.get_feature_dependencies(child_db.id)
        assert len(db_deps) == 0  # No dependencies for the first child

        # ---- Step 6: Complete children in order ----
        # Complete Database Schema (no dependencies, can go first)
        db.update_feature(child_db.id, status="completed")
        assert db.get_feature(child_db.id).status == "completed"

        # Parent should NOT be completed yet (2 children still pending)
        result = db.check_parent_completion(child_db.id)
        assert result is False
        assert db.get_feature(parent.id).status == "pending_decomposition"

        # Complete API Endpoints (depends on Database, which is done)
        db.update_feature(child_api.id, status="completed")
        assert db.get_feature(child_api.id).status == "completed"

        # Parent should still NOT be completed (1 child remaining)
        result = db.check_parent_completion(child_api.id)
        assert result is False
        assert db.get_feature(parent.id).status == "pending_decomposition"

        # Complete Frontend Integration (depends on API, which is done)
        db.update_feature(child_fe.id, status="completed")
        assert db.get_feature(child_fe.id).status == "completed"

        # ---- Step 7: Verify parent marked complete ----
        result = db.check_parent_completion(child_fe.id)
        assert result is True

        final_parent = db.get_feature(parent.id)
        assert final_parent.status == "completed"

        # Verify all children are still completed
        final_children = db.get_child_features(parent.id)
        assert len(final_children) == 3
        assert all(c.status == "completed" for c in final_children)

    def test_failed_child_prevents_parent_completion(self, tmp_db):
        """Parent stays pending_decomposition if any child has failed."""
        project = db.create_project(
            name="failed-child-project",
            workspace_path="/tmp/failed-child-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="pending_decomposition",
        )

        child_a = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child A",
            status="completed",
        )
        child_b = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child B",
            status="completed",
        )
        child_c = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child C",
            status="failed",  # This child failed
        )

        # Even though 2 of 3 are completed, parent should NOT auto-complete
        result = db.check_parent_completion(child_b.id)
        assert result is False
        assert db.get_feature(parent.id).status == "pending_decomposition"

    def test_parent_not_in_pending_decomposition_not_completed(self, tmp_db):
        """Only parents with status 'pending_decomposition' can auto-complete."""
        project = db.create_project(
            name="wrong-status-project",
            workspace_path="/tmp/wrong-status-ws",
        )
        parent = db.create_feature(
            project_id=project.id,
            name="Parent Feature",
            status="executing",  # Not pending_decomposition
        )

        child = db.create_child_feature(
            parent_feature_id=parent.id,
            project_id=project.id,
            name="Child A",
            status="completed",
        )

        result = db.check_parent_completion(child.id)
        assert result is False
        assert db.get_feature(parent.id).status == "executing"
