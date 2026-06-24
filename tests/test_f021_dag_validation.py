"""Tests for F021: Feature dependency DAG validation (no cycles)."""

import pathlib

import pytest


WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database

    init_database()
    return p


@pytest.fixture()
def project_id(db_path):
    """Create a project and return its ID for use as a foreign key."""
    from bob.db import create_project

    project = create_project(
        name="Test Project",
        workspace_path="/tmp/test",
    )
    return project.id


# ============================================================
# Step 1: validate_dependencies() function exists in db.py
# ============================================================


class TestValidateDependenciesExists:
    """validate_dependencies() is importable and callable."""

    def test_validate_dependencies_importable(self, db_path):
        from bob.db import validate_dependencies

        assert callable(validate_dependencies)

    def test_validate_dependencies_accepts_project_id(self, db_path, project_id):
        from bob.db import validate_dependencies

        result = validate_dependencies(project_id)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_validate_dependencies_returns_bool_and_list(self, db_path, project_id):
        from bob.db import validate_dependencies

        is_valid, cycle = validate_dependencies(project_id)
        assert isinstance(is_valid, bool)
        assert isinstance(cycle, list)


# ============================================================
# Step 2: Cycle detection using DFS
# ============================================================


class TestCycleDetectionDFS:
    """validate_dependencies() detects cycles using DFS."""

    def test_no_features_is_valid(self, db_path, project_id):
        from bob.db import validate_dependencies

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is True
        assert cycle == []

    def test_single_feature_no_deps_is_valid(self, db_path, project_id):
        from bob.db import create_feature, validate_dependencies

        create_feature(project_id=project_id, name="Standalone")
        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is True
        assert cycle == []

    def test_features_no_deps_is_valid(self, db_path, project_id):
        from bob.db import create_feature, validate_dependencies

        create_feature(project_id=project_id, name="A")
        create_feature(project_id=project_id, name="B")
        create_feature(project_id=project_id, name="C")

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is True
        assert cycle == []

    def test_direct_cycle_detected(self, db_path, project_id):
        """A -> B -> A should be detected as a cycle."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        # Create the cycle: A depends on B, but B already depends on A
        add_feature_dependency(feature_id=fa.id, depends_on_feature_id=fb.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is False
        assert len(cycle) >= 2
        # The cycle should contain both feature IDs
        assert fa.id in cycle
        assert fb.id in cycle

    def test_indirect_cycle_detected(self, db_path, project_id):
        """A -> B -> C -> A should be detected."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fb.id)
        add_feature_dependency(feature_id=fa.id, depends_on_feature_id=fc.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is False
        assert len(cycle) >= 3
        assert fa.id in cycle
        assert fb.id in cycle
        assert fc.id in cycle

    def test_self_dependency_detected(self, db_path, project_id):
        """A -> A should be detected as a cycle."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        fa = create_feature(project_id=project_id, name="Self-dep")
        add_feature_dependency(feature_id=fa.id, depends_on_feature_id=fa.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is False
        assert fa.id in cycle


# ============================================================
# Step 3: Valid dependency chain passes
# ============================================================


class TestValidDependencyChain:
    """Valid dependency chains pass validation."""

    def test_linear_chain_is_valid(self, db_path, project_id):
        """A -> B -> C (no cycle) should pass."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fb.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is True
        assert cycle == []

    def test_diamond_dependency_is_valid(self, db_path, project_id):
        """Diamond: A -> B, A -> C, B -> D, C -> D (no cycle) should pass."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")
        fd = create_feature(project_id=project_id, name="D")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fd.id, depends_on_feature_id=fb.id)
        add_feature_dependency(feature_id=fd.id, depends_on_feature_id=fc.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is True
        assert cycle == []

    def test_multiple_roots_is_valid(self, db_path, project_id):
        """Multiple disconnected trees are valid."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")
        fd = create_feature(project_id=project_id, name="D")

        # Tree 1: A -> B
        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        # Tree 2: C -> D
        add_feature_dependency(feature_id=fd.id, depends_on_feature_id=fc.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is True
        assert cycle == []

    def test_only_checks_project_features(self, db_path):
        """Dependencies in other projects don't affect validation."""
        from bob.db import (
            create_feature,
            create_project,
            add_feature_dependency,
            validate_dependencies,
        )

        p1 = create_project(name="Project 1", workspace_path="/tmp/p1")
        p2 = create_project(name="Project 2", workspace_path="/tmp/p2")

        # Create a cycle in project 2
        fa = create_feature(project_id=p2.id, name="X")
        fb = create_feature(project_id=p2.id, name="Y")
        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fa.id, depends_on_feature_id=fb.id)

        # Project 1 should be valid (no features)
        is_valid, cycle = validate_dependencies(p1.id)
        assert is_valid is True
        assert cycle == []


# ============================================================
# Step 4: Circular dependency is rejected (already covered above,
#         but add a couple more edge-case tests)
# ============================================================


class TestCircularDependencyRejection:
    """Edge cases for circular dependency detection."""

    def test_long_cycle_detected(self, db_path, project_id):
        """A -> B -> C -> D -> E -> A should be detected."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        features = []
        for name in ["A", "B", "C", "D", "E"]:
            f = create_feature(project_id=project_id, name=name)
            features.append(f)

        for i in range(len(features) - 1):
            add_feature_dependency(
                feature_id=features[i + 1].id,
                depends_on_feature_id=features[i].id,
            )
        # Close the cycle
        add_feature_dependency(
            feature_id=features[0].id,
            depends_on_feature_id=features[-1].id,
        )

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is False
        assert len(cycle) >= 2

    def test_cycle_in_subgraph_detected(self, db_path, project_id):
        """Cycle in a subgraph with valid nodes elsewhere."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            validate_dependencies,
        )

        # Valid chain: V1 -> V2
        v1 = create_feature(project_id=project_id, name="V1")
        v2 = create_feature(project_id=project_id, name="V2")
        add_feature_dependency(feature_id=v2.id, depends_on_feature_id=v1.id)

        # Cycle: C1 -> C2 -> C1
        c1 = create_feature(project_id=project_id, name="C1")
        c2 = create_feature(project_id=project_id, name="C2")
        add_feature_dependency(feature_id=c2.id, depends_on_feature_id=c1.id)
        add_feature_dependency(feature_id=c1.id, depends_on_feature_id=c2.id)

        is_valid, cycle = validate_dependencies(project_id)
        assert is_valid is False
        assert c1.id in cycle or c2.id in cycle


# ============================================================
# Step 5: get_all_predecessors() helper
# ============================================================


class TestGetAllPredecessors:
    """get_all_predecessors() returns all transitive dependencies."""

    def test_get_all_predecessors_importable(self, db_path):
        from bob.db import get_all_predecessors

        assert callable(get_all_predecessors)

    def test_no_predecessors(self, db_path, project_id):
        from bob.db import create_feature, get_all_predecessors

        fa = create_feature(project_id=project_id, name="Root")
        predecessors = get_all_predecessors(fa.id)
        assert predecessors == set()

    def test_direct_predecessors(self, db_path, project_id):
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_all_predecessors,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)

        predecessors = get_all_predecessors(fb.id)
        assert predecessors == {fa.id}

    def test_transitive_predecessors(self, db_path, project_id):
        """A -> B -> C: predecessors of C should be {A, B}."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_all_predecessors,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fb.id)

        predecessors = get_all_predecessors(fc.id)
        assert predecessors == {fa.id, fb.id}

    def test_diamond_predecessors(self, db_path, project_id):
        """Diamond: D depends on B and C, both depend on A."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_all_predecessors,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")
        fd = create_feature(project_id=project_id, name="D")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fd.id, depends_on_feature_id=fb.id)
        add_feature_dependency(feature_id=fd.id, depends_on_feature_id=fc.id)

        predecessors = get_all_predecessors(fd.id)
        assert predecessors == {fa.id, fb.id, fc.id}

    def test_predecessors_of_root_in_chain(self, db_path, project_id):
        """A -> B -> C: predecessors of A should be empty."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_all_predecessors,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fb.id)

        predecessors = get_all_predecessors(fa.id)
        assert predecessors == set()

    def test_predecessors_middle_of_chain(self, db_path, project_id):
        """A -> B -> C: predecessors of B should be {A}."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_all_predecessors,
        )

        fa = create_feature(project_id=project_id, name="A")
        fb = create_feature(project_id=project_id, name="B")
        fc = create_feature(project_id=project_id, name="C")

        add_feature_dependency(feature_id=fb.id, depends_on_feature_id=fa.id)
        add_feature_dependency(feature_id=fc.id, depends_on_feature_id=fb.id)

        predecessors = get_all_predecessors(fb.id)
        assert predecessors == {fa.id}

    def test_deep_transitive_predecessors(self, db_path, project_id):
        """A -> B -> C -> D -> E: predecessors of E should be {A,B,C,D}."""
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_all_predecessors,
        )

        features = []
        for name in ["A", "B", "C", "D", "E"]:
            f = create_feature(project_id=project_id, name=name)
            features.append(f)

        for i in range(len(features) - 1):
            add_feature_dependency(
                feature_id=features[i + 1].id,
                depends_on_feature_id=features[i].id,
            )

        predecessors = get_all_predecessors(features[-1].id)
        expected = {f.id for f in features[:-1]}
        assert predecessors == expected
