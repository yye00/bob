"""Tests for F059: Track sub-agent hierarchy (parent_run_id).

Validates that:
- Step 1: When spawning sub-agent from another agent, set parent_run_id
- Step 2: get_agent_hierarchy() function queries the tree
- Step 3: Spawn agent A, then B from A, then C from B
- Step 4: parent_run_id links form correct tree
"""

from datetime import datetime

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
    """Create a test project."""
    return db.create_project(
        name="Hierarchy Test Project",
        workspace_path="/tmp/hierarchy-test",
    )


# ===================================================================
# Step 1: When spawning sub-agent from another agent, set parent_run_id
# ===================================================================


class TestParentRunIdSet:
    """Step 1: parent_run_id is correctly set when spawning child agents."""

    def test_create_agent_run_with_parent(self, project):
        """Creating an agent run with parent_run_id stores the link."""
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

    def test_create_agent_run_without_parent(self, project):
        """Creating a root agent run has None for parent_run_id."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        assert root.parent_run_id is None

    def test_parent_run_id_persisted(self, project):
        """parent_run_id is persisted and retrievable from database."""
        parent = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        child = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=parent.id,
        )

        retrieved = db.get_agent_run(child.id)
        assert retrieved is not None
        assert retrieved.parent_run_id == parent.id

    def test_query_agent_runs_by_parent(self, project):
        """query_agent_runs can filter by parent_run_id."""
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
            purpose="validate_feature",
            parent_run_id=parent.id,
        )
        # Unrelated root agent
        db.create_agent_run(
            project_id=project.id,
            purpose="other_root",
        )

        children = db.query_agent_runs(
            project_id=project.id,
            parent_run_id=parent.id,
        )
        assert len(children) == 2
        child_ids = {c.id for c in children}
        assert child1.id in child_ids
        assert child2.id in child_ids


# ===================================================================
# Step 2: get_agent_hierarchy() function to query tree
# ===================================================================


class TestGetAgentHierarchy:
    """Step 2: get_agent_hierarchy() returns the full tree for a run."""

    def test_function_exists(self):
        """get_agent_hierarchy exists in db module."""
        assert hasattr(db, "get_agent_hierarchy")
        assert callable(db.get_agent_hierarchy)

    def test_single_root_returns_itself(self, project):
        """A root agent with no children returns just itself."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )

        hierarchy = db.get_agent_hierarchy(root.id)
        assert len(hierarchy) == 1
        assert hierarchy[0].id == root.id

    def test_root_with_children(self, project):
        """A root agent with two children returns all three."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        child1 = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=root.id,
        )
        child2 = db.create_agent_run(
            project_id=project.id,
            purpose="validate_feature",
            parent_run_id=root.id,
        )

        hierarchy = db.get_agent_hierarchy(root.id)
        assert len(hierarchy) == 3
        ids = {h.id for h in hierarchy}
        assert root.id in ids
        assert child1.id in ids
        assert child2.id in ids

    def test_returns_none_for_missing_run(self):
        """get_agent_hierarchy returns None for non-existent run."""
        result = db.get_agent_hierarchy("nonexistent-id")
        assert result is None

    def test_hierarchy_order_root_first(self, project):
        """Hierarchy is returned with the root as the first element."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=root.id,
        )

        hierarchy = db.get_agent_hierarchy(root.id)
        assert hierarchy[0].id == root.id

    def test_called_from_child_returns_subtree(self, project):
        """Calling get_agent_hierarchy on a child returns just its subtree."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        child = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=root.id,
        )
        grandchild = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            parent_run_id=child.id,
        )

        hierarchy = db.get_agent_hierarchy(child.id)
        assert len(hierarchy) == 2
        ids = {h.id for h in hierarchy}
        assert child.id in ids
        assert grandchild.id in ids
        assert root.id not in ids


# ===================================================================
# Step 3: Spawn agent A, then B from A, then C from B
# ===================================================================


class TestThreeLevelHierarchy:
    """Step 3: Three-level hierarchy (A -> B -> C)."""

    def test_three_level_chain(self, project):
        """Create a three-level chain and verify all links."""
        agent_a = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        agent_b = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=agent_a.id,
        )
        agent_c = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            parent_run_id=agent_b.id,
        )

        assert agent_a.parent_run_id is None
        assert agent_b.parent_run_id == agent_a.id
        assert agent_c.parent_run_id == agent_b.id

    def test_three_level_hierarchy_from_root(self, project):
        """get_agent_hierarchy from root returns all three levels."""
        agent_a = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        agent_b = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=agent_a.id,
        )
        agent_c = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            parent_run_id=agent_b.id,
        )

        hierarchy = db.get_agent_hierarchy(agent_a.id)
        assert len(hierarchy) == 3
        ids = [h.id for h in hierarchy]
        assert ids[0] == agent_a.id  # Root first
        assert agent_b.id in ids
        assert agent_c.id in ids


# ===================================================================
# Step 4: Verify parent_run_id links form correct tree
# ===================================================================


class TestTreeStructureCorrectness:
    """Step 4: Verify parent_run_id links form correct tree structure."""

    def test_branching_tree(self, project):
        """A branching tree: root -> (child1, child2), child1 -> grandchild."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        child1 = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=root.id,
        )
        child2 = db.create_agent_run(
            project_id=project.id,
            purpose="validate_feature",
            parent_run_id=root.id,
        )
        grandchild = db.create_agent_run(
            project_id=project.id,
            purpose="rca_analyst",
            parent_run_id=child1.id,
        )

        hierarchy = db.get_agent_hierarchy(root.id)
        assert len(hierarchy) == 4

        # Verify the tree structure by checking parent_run_ids
        run_map = {h.id: h for h in hierarchy}
        assert run_map[root.id].parent_run_id is None
        assert run_map[child1.id].parent_run_id == root.id
        assert run_map[child2.id].parent_run_id == root.id
        assert run_map[grandchild.id].parent_run_id == child1.id

    def test_separate_trees_isolated(self, project):
        """Two separate trees don't overlap in hierarchy queries."""
        tree1_root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        tree1_child = db.create_agent_run(
            project_id=project.id,
            purpose="implement_feature",
            parent_run_id=tree1_root.id,
        )

        tree2_root = db.create_agent_run(
            project_id=project.id,
            purpose="orchestrator",
        )
        tree2_child = db.create_agent_run(
            project_id=project.id,
            purpose="validate_feature",
            parent_run_id=tree2_root.id,
        )

        hierarchy1 = db.get_agent_hierarchy(tree1_root.id)
        hierarchy2 = db.get_agent_hierarchy(tree2_root.id)

        ids1 = {h.id for h in hierarchy1}
        ids2 = {h.id for h in hierarchy2}

        assert tree1_root.id in ids1
        assert tree1_child.id in ids1
        assert tree2_root.id not in ids1
        assert tree2_child.id not in ids1

        assert tree2_root.id in ids2
        assert tree2_child.id in ids2
        assert tree1_root.id not in ids2
        assert tree1_child.id not in ids2

    def test_deep_hierarchy_five_levels(self, project):
        """A five-level deep hierarchy is correctly tracked."""
        agents = []
        parent_id = None
        for i in range(5):
            agent = db.create_agent_run(
                project_id=project.id,
                purpose=f"level_{i}",
                parent_run_id=parent_id,
            )
            agents.append(agent)
            parent_id = agent.id

        # Full hierarchy from root
        hierarchy = db.get_agent_hierarchy(agents[0].id)
        assert len(hierarchy) == 5

        # Verify chain
        for i in range(1, 5):
            run = next(h for h in hierarchy if h.id == agents[i].id)
            assert run.parent_run_id == agents[i - 1].id

    def test_child_count_at_each_level(self, project):
        """Verify child counts at each level of a complex tree."""
        root = db.create_agent_run(
            project_id=project.id,
            purpose="root",
        )
        # 3 children of root
        children = []
        for i in range(3):
            child = db.create_agent_run(
                project_id=project.id,
                purpose=f"child_{i}",
                parent_run_id=root.id,
            )
            children.append(child)

        # 2 grandchildren from first child
        for i in range(2):
            db.create_agent_run(
                project_id=project.id,
                purpose=f"grandchild_{i}",
                parent_run_id=children[0].id,
            )

        hierarchy = db.get_agent_hierarchy(root.id)
        assert len(hierarchy) == 6  # 1 root + 3 children + 2 grandchildren

        # Only first child's subtree should include grandchildren
        child0_hierarchy = db.get_agent_hierarchy(children[0].id)
        assert len(child0_hierarchy) == 3  # child0 + 2 grandchildren

        child1_hierarchy = db.get_agent_hierarchy(children[1].id)
        assert len(child1_hierarchy) == 1  # Just child1, no descendants
