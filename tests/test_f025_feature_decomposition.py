"""Tests for F025: Feature decomposition tracking (parent/child relationships).

Tests create_child_feature(), get_child_features(), decomposition_depth tracking,
and max depth limit enforcement (3 levels).
"""

import pathlib
import tempfile

import pytest

from bob import db


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    """Set up a temporary database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "get_database_path", lambda: db_path)
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture
def project():
    """Create a test project."""
    return db.create_project(name="test-project", workspace_path="/tmp/test")


@pytest.fixture
def parent_feature(project):
    """Create a parent feature."""
    return db.create_feature(
        project_id=project.id,
        name="Parent Feature",
        description="A top-level feature",
    )


# ============================================================
# Step 1: create_child_feature() sets parent_feature_id
# ============================================================


class TestCreateChildFeature:
    """Test create_child_feature() function."""

    def test_creates_child_with_parent_id(self, project, parent_feature):
        """Child feature has correct parent_feature_id."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child Feature",
        )
        assert child.parent_feature_id == parent_feature.id

    def test_child_inherits_project_id(self, project, parent_feature):
        """Child feature inherits the project_id from the parent."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child Feature",
        )
        assert child.project_id == project.id

    def test_child_has_depth_1(self, project, parent_feature):
        """Child of root feature has decomposition_depth=1."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child Feature",
        )
        assert child.decomposition_depth == 1

    def test_child_persisted_in_db(self, project, parent_feature):
        """Child feature is persisted and retrievable from the database."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child Feature",
        )
        retrieved = db.get_feature(child.id)
        assert retrieved is not None
        assert retrieved.parent_feature_id == parent_feature.id
        assert retrieved.decomposition_depth == 1

    def test_child_accepts_optional_fields(self, project, parent_feature):
        """Child feature accepts optional fields like description and priority."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child Feature",
            description="Detailed description",
            acceptance_criteria='["criterion 1"]',
            priority=50,
            risk_category="high",
        )
        assert child.description == "Detailed description"
        assert child.acceptance_criteria == '["criterion 1"]'
        assert child.priority == 50
        assert child.risk_category == "high"

    def test_raises_on_invalid_parent(self, project):
        """Raises ValueError when parent feature does not exist."""
        with pytest.raises(ValueError, match="Parent feature .* not found"):
            db.create_child_feature(
                parent_feature_id="nonexistent-id",
                project_id=project.id,
                name="Orphan Feature",
            )


# ============================================================
# Step 2: get_child_features() function
# ============================================================


class TestGetChildFeatures:
    """Test get_child_features() function."""

    def test_returns_empty_for_no_children(self, project, parent_feature):
        """Returns empty list when feature has no children."""
        children = db.get_child_features(parent_feature.id)
        assert children == []

    def test_returns_children(self, project, parent_feature):
        """Returns all child features of a parent."""
        child1 = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child 1",
        )
        child2 = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child 2",
        )
        children = db.get_child_features(parent_feature.id)
        assert len(children) == 2
        child_ids = {c.id for c in children}
        assert child1.id in child_ids
        assert child2.id in child_ids

    def test_does_not_return_grandchildren(self, project, parent_feature):
        """get_child_features only returns direct children, not grandchildren."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child",
        )
        db.create_child_feature(
            parent_feature_id=child.id,
            project_id=project.id,
            name="Grandchild",
        )
        children = db.get_child_features(parent_feature.id)
        assert len(children) == 1
        assert children[0].id == child.id


# ============================================================
# Step 3: decomposition_depth tracking
# ============================================================


class TestDecompositionDepth:
    """Test decomposition_depth tracking across levels."""

    def test_root_feature_has_depth_0(self, parent_feature):
        """Root features have decomposition_depth=0."""
        assert parent_feature.decomposition_depth == 0

    def test_child_has_depth_1(self, project, parent_feature):
        """Direct child has decomposition_depth=1."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child",
        )
        assert child.decomposition_depth == 1

    def test_grandchild_has_depth_2(self, project, parent_feature):
        """Grandchild has decomposition_depth=2."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Child",
        )
        grandchild = db.create_child_feature(
            parent_feature_id=child.id,
            project_id=project.id,
            name="Grandchild",
        )
        assert grandchild.decomposition_depth == 2

    def test_great_grandchild_has_depth_3(self, project, parent_feature):
        """Great-grandchild at max depth has decomposition_depth=3."""
        child = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Level 1",
        )
        grandchild = db.create_child_feature(
            parent_feature_id=child.id,
            project_id=project.id,
            name="Level 2",
        )
        great_grandchild = db.create_child_feature(
            parent_feature_id=grandchild.id,
            project_id=project.id,
            name="Level 3",
        )
        assert great_grandchild.decomposition_depth == 3


# ============================================================
# Steps 4 & 5: Create parent + 3 children, verify relationships
# ============================================================


class TestParentWith3Children:
    """Test creating a parent feature with 3 child features."""

    def test_create_parent_and_3_children(self, project, parent_feature):
        """Create a parent feature and 3 child features."""
        children = []
        for i in range(3):
            child = db.create_child_feature(
                parent_feature_id=parent_feature.id,
                project_id=project.id,
                name=f"Child {i + 1}",
            )
            children.append(child)

        # All children should reference the parent
        for child in children:
            assert child.parent_feature_id == parent_feature.id
            assert child.decomposition_depth == 1
            assert child.project_id == project.id

        # Querying children should return all 3
        db_children = db.get_child_features(parent_feature.id)
        assert len(db_children) == 3

    def test_children_retrievable_from_db(self, project, parent_feature):
        """All child features are retrievable and have correct attributes."""
        names = ["Auth Module", "Storage Module", "API Module"]
        created = []
        for name in names:
            child = db.create_child_feature(
                parent_feature_id=parent_feature.id,
                project_id=project.id,
                name=name,
            )
            created.append(child)

        for child in created:
            retrieved = db.get_feature(child.id)
            assert retrieved is not None
            assert retrieved.parent_feature_id == parent_feature.id
            assert retrieved.decomposition_depth == 1
            assert retrieved.name in names


# ============================================================
# Step 6: Max depth limit (3 levels)
# ============================================================


class TestMaxDepthLimit:
    """Test max depth limit enforcement (3 levels)."""

    def test_depth_3_is_allowed(self, project, parent_feature):
        """Decomposition to depth 3 is allowed."""
        level1 = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Level 1",
        )
        level2 = db.create_child_feature(
            parent_feature_id=level1.id,
            project_id=project.id,
            name="Level 2",
        )
        level3 = db.create_child_feature(
            parent_feature_id=level2.id,
            project_id=project.id,
            name="Level 3",
        )
        assert level3.decomposition_depth == 3

    def test_depth_4_raises_error(self, project, parent_feature):
        """Decomposition beyond depth 3 raises ValueError."""
        level1 = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Level 1",
        )
        level2 = db.create_child_feature(
            parent_feature_id=level1.id,
            project_id=project.id,
            name="Level 2",
        )
        level3 = db.create_child_feature(
            parent_feature_id=level2.id,
            project_id=project.id,
            name="Level 3",
        )
        with pytest.raises(ValueError, match="Maximum decomposition depth.*exceeded"):
            db.create_child_feature(
                parent_feature_id=level3.id,
                project_id=project.id,
                name="Level 4 - Too Deep",
            )

    def test_multiple_children_at_max_depth(self, project, parent_feature):
        """Multiple children can be created at the max depth level."""
        level1 = db.create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project.id,
            name="Level 1",
        )
        level2 = db.create_child_feature(
            parent_feature_id=level1.id,
            project_id=project.id,
            name="Level 2",
        )
        # Create multiple children at depth 3
        for i in range(3):
            child = db.create_child_feature(
                parent_feature_id=level2.id,
                project_id=project.id,
                name=f"Level 3 Child {i + 1}",
            )
            assert child.decomposition_depth == 3

        children = db.get_child_features(level2.id)
        assert len(children) == 3
