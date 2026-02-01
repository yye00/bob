"""Tests for the DAG validator module."""

import pytest
from unittest.mock import MagicMock
from bob.orchestrator.dag_validator import (
    validate_work_unit_dag,
    validate_task_dependencies,
    DAGValidationResult,
)


class FakeWorkUnit:
    """Minimal WorkUnit stand-in for testing."""

    def __init__(self, uid, parent_id=None, children=None, content=None, depth=0):
        self.id = uid
        self.parent_id = parent_id
        self.children = children or []
        self.content = content or {}
        self.depth = depth


# ---------------------------------------------------------------------------
# validate_task_dependencies
# ---------------------------------------------------------------------------


class TestValidateTaskDependencies:
    def test_empty_list(self):
        result = validate_task_dependencies([])
        assert result.valid
        assert result.stats["tasks"] == 0

    def test_no_dependencies(self):
        tasks = [
            {"id": "T001", "title": "A"},
            {"id": "T002", "title": "B"},
        ]
        result = validate_task_dependencies(tasks)
        assert result.valid
        assert result.stats["tasks"] == 2
        assert result.stats["dependencies"] == 0

    def test_valid_chain(self):
        tasks = [
            {"id": "T001", "title": "A", "depends_on": []},
            {"id": "T002", "title": "B", "depends_on": ["T001"]},
            {"id": "T003", "title": "C", "depends_on": ["T001", "T002"]},
        ]
        result = validate_task_dependencies(tasks)
        assert result.valid
        assert result.stats["has_valid_ordering"]

    def test_circular_dependency(self):
        tasks = [
            {"id": "T001", "depends_on": ["T003"]},
            {"id": "T002", "depends_on": ["T001"]},
            {"id": "T003", "depends_on": ["T002"]},
        ]
        result = validate_task_dependencies(tasks)
        assert not result.valid
        assert any("Circular" in e for e in result.errors)

    def test_missing_dependency(self):
        tasks = [
            {"id": "T001", "depends_on": ["T999"]},
        ]
        result = validate_task_dependencies(tasks)
        assert not result.valid
        assert any("T999" in e for e in result.errors)

    def test_duplicate_ids(self):
        tasks = [
            {"id": "T001", "title": "A"},
            {"id": "T001", "title": "B"},
        ]
        result = validate_task_dependencies(tasks)
        assert not result.valid
        assert any("Duplicate" in e for e in result.errors)

    def test_self_dependency(self):
        tasks = [
            {"id": "T001", "depends_on": ["T001"]},
        ]
        result = validate_task_dependencies(tasks)
        assert not result.valid
        assert any("Circular" in e for e in result.errors)


# ---------------------------------------------------------------------------
# validate_work_unit_dag
# ---------------------------------------------------------------------------


class TestValidateWorkUnitDag:
    def test_empty_tree(self):
        result = validate_work_unit_dag({})
        assert result.valid
        assert result.stats["nodes"] == 0

    def test_single_root(self):
        tree = {
            "root": FakeWorkUnit("root"),
        }
        result = validate_work_unit_dag(tree)
        assert result.valid
        assert result.stats["roots"] == 1

    def test_valid_tree(self):
        tree = {
            "root": FakeWorkUnit("root", children=["c1", "c2"]),
            "c1": FakeWorkUnit("c1", parent_id="root"),
            "c2": FakeWorkUnit("c2", parent_id="root"),
        }
        result = validate_work_unit_dag(tree)
        assert result.valid
        assert result.stats["nodes"] == 3
        assert result.stats["roots"] == 1

    def test_missing_parent(self):
        tree = {
            "c1": FakeWorkUnit("c1", parent_id="nonexistent"),
        }
        result = validate_work_unit_dag(tree)
        assert not result.valid
        assert any("nonexistent" in e for e in result.errors)

    def test_missing_child(self):
        tree = {
            "root": FakeWorkUnit("root", children=["ghost"]),
        }
        result = validate_work_unit_dag(tree)
        assert not result.valid
        assert any("ghost" in e for e in result.errors)

    def test_orphan_detection(self):
        tree = {
            "root": FakeWorkUnit("root"),
            "orphan": FakeWorkUnit("orphan"),  # No parent, but also a root
        }
        # Both have no parent → both are roots → both reachable
        result = validate_work_unit_dag(tree)
        assert result.valid
        assert result.stats["roots"] == 2

    def test_unreachable_node(self):
        # A node with a parent that exists but doesn't list it as child
        tree = {
            "root": FakeWorkUnit("root"),
            "child": FakeWorkUnit("child", parent_id="root"),
        }
        # child has parent=root, root doesn't have child in children
        # child IS reachable because we walk children, but root has no children
        result = validate_work_unit_dag(tree)
        assert result.valid  # No cycle, parent exists
        # But child won't be reachable from root via children walk
        assert result.stats["orphans"] == 1 or len(result.warnings) > 0

    def test_content_depends_on_validation(self):
        tree = {
            "u1": FakeWorkUnit("u1", content={"id": "T001", "depends_on": []}),
            "u2": FakeWorkUnit("u2", content={"id": "T002", "depends_on": ["T001"]}),
            "u3": FakeWorkUnit("u3", content={"id": "T003", "depends_on": ["T999"]}),
        }
        result = validate_work_unit_dag(tree, check_content_deps=True)
        # T999 doesn't exist → warning
        assert any("T999" in w for w in result.warnings)

    def test_deep_tree(self):
        tree = {}
        prev = None
        for i in range(10):
            uid = f"u{i}"
            tree[uid] = FakeWorkUnit(
                uid,
                parent_id=prev,
                children=[f"u{i+1}"] if i < 9 else [],
                depth=i,
            )
            prev = uid

        result = validate_work_unit_dag(tree)
        assert result.valid
        assert result.stats["max_depth"] == 9


class TestDAGValidationResult:
    def test_str_valid(self):
        r = DAGValidationResult()
        r.stats = {"nodes": 5}
        assert "valid" in str(r).lower()

    def test_str_invalid(self):
        r = DAGValidationResult()
        r.add_error("broken")
        assert "INVALID" in str(r)
        assert "broken" in str(r)
