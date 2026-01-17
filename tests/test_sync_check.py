"""Tests for sync check utilities.

Tests sync hash tracking, change detection, and sync prompting.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bob.database import DatabaseManager
from bob.models.base import Project, ProjectStatus
from bob.utils.sync_check import (
    SyncCheckResult,
    check_sync_needed,
    compute_spec_source_hash,
    update_sync_hash,
)


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(db_path)
        yield manager


@pytest.fixture
def spec_file():
    """Create a temporary spec file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = Path(tmpdir) / "spec.yaml"
        spec_path.write_text("""
version: 1
features:
  - id: F001
    title: Test Feature
    description: A test feature
    priority: high
""")
        yield spec_path


@pytest.fixture
def sample_project(spec_file):
    """Create a sample project."""
    return Project(
        id="proj-test-001",
        name="test-project",
        description="Test project",
        workspace_dir="/tmp/test-workspace",
        spec_source=f"file://{spec_file}",
        status=ProjectStatus.ACTIVE,
    )


class TestSyncCheckResult:
    """Test SyncCheckResult class."""

    def test_sync_check_result_needed(self):
        """Test SyncCheckResult when sync is needed."""
        result = SyncCheckResult(
            sync_needed=True,
            current_hash="abc123",
            last_sync_hash="def456",
            reason="Spec source has changed",
        )
        assert result.sync_needed is True
        assert bool(result) is True
        assert result.current_hash == "abc123"
        assert result.last_sync_hash == "def456"
        assert result.reason == "Spec source has changed"

    def test_sync_check_result_not_needed(self):
        """Test SyncCheckResult when sync is not needed."""
        result = SyncCheckResult(
            sync_needed=False,
            current_hash="abc123",
            last_sync_hash="abc123",
        )
        assert result.sync_needed is False
        assert bool(result) is False

    def test_sync_check_result_default_reason(self):
        """Test SyncCheckResult with default reason."""
        result = SyncCheckResult(sync_needed=False)
        assert result.reason == "Spec source has not changed"


class TestComputeSpecSourceHash:
    """Test compute_spec_source_hash function."""

    def test_compute_hash_for_file_source(self, sample_project, spec_file):
        """Test computing hash for file-based spec source."""
        hash1 = compute_spec_source_hash(sample_project)
        assert hash1 is not None
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA256 hex digest

        # Computing again should give same hash
        hash2 = compute_spec_source_hash(sample_project)
        assert hash1 == hash2

    def test_compute_hash_changes_when_file_changes(self, sample_project, spec_file):
        """Test that hash changes when spec file changes."""
        hash1 = compute_spec_source_hash(sample_project)

        # Modify the spec file
        spec_file.write_text("""
version: 1
features:
  - id: F001
    title: Updated Feature
    description: An updated feature
    priority: critical
""")

        hash2 = compute_spec_source_hash(sample_project)
        assert hash1 != hash2

    def test_compute_hash_for_unsupported_source(self):
        """Test computing hash for unsupported source type."""
        project = Project(
            id="proj-001",
            name="test",
            description="test",
            workspace_dir="/tmp/test",
            spec_source="jira://project/issues",  # Jira not yet implemented
            status=ProjectStatus.ACTIVE,
        )

        with pytest.raises(ValueError, match="No spec source registered"):
            compute_spec_source_hash(project)


class TestCheckSyncNeeded:
    """Test check_sync_needed function."""

    def test_sync_needed_never_synced(self, sample_project):
        """Test that sync is needed for project that was never synced."""
        # Project with no last_sync_hash
        result = check_sync_needed(sample_project)

        assert result.sync_needed is True
        assert result.reason == "Project has never been synced"
        assert result.last_sync_hash is None
        assert result.last_sync_at is None

    def test_sync_needed_spec_changed(self, sample_project, spec_file):
        """Test that sync is needed when spec changes."""
        # Set last_sync_hash to original hash
        original_hash = compute_spec_source_hash(sample_project)
        sample_project.last_sync_hash = original_hash
        sample_project.last_sync_at = datetime.now()

        # Verify no sync needed initially
        result = check_sync_needed(sample_project)
        assert result.sync_needed is False

        # Modify spec file
        spec_file.write_text("""
version: 2
features:
  - id: F001
    title: Updated Feature
    description: Updated
    priority: critical
  - id: F002
    title: New Feature
    description: New
    priority: high
""")

        # Now sync should be needed
        result = check_sync_needed(sample_project)
        assert result.sync_needed is True
        assert result.reason == "Spec source has changed since last sync"
        assert result.current_hash != result.last_sync_hash

    def test_sync_not_needed_no_changes(self, sample_project):
        """Test that sync is not needed when spec hasn't changed."""
        # Set last_sync_hash to current hash
        current_hash = compute_spec_source_hash(sample_project)
        sample_project.last_sync_hash = current_hash
        sample_project.last_sync_at = datetime.now()

        result = check_sync_needed(sample_project)

        assert result.sync_needed is False
        assert result.reason == "Spec source is up to date"
        assert result.current_hash == result.last_sync_hash

    def test_sync_needed_cannot_compute_hash(self, spec_file):
        """Test that sync is needed if hash cannot be computed."""
        # Create project with non-existent file
        project = Project(
            id="proj-001",
            name="test",
            description="test",
            workspace_dir="/tmp/test",
            spec_source="file:///nonexistent/path/spec.yaml",
            status=ProjectStatus.ACTIVE,
            last_sync_hash="some-old-hash",
            last_sync_at=datetime.now() - timedelta(hours=1),
        )

        result = check_sync_needed(project)

        assert result.sync_needed is True
        assert "Cannot compute spec source hash" in result.reason


class TestUpdateSyncHash:
    """Test update_sync_hash function."""

    def test_update_sync_hash(self, db, sample_project, spec_file):
        """Test updating sync hash after sync."""
        # Create project in database
        db.create_project(sample_project)

        # Verify initial state
        assert sample_project.last_sync_hash is None
        assert sample_project.last_sync_at is None

        # Update sync hash
        update_sync_hash(db, sample_project)

        # Verify hash was updated in database
        updated_project = db.get_project(sample_project.id)
        assert updated_project is not None
        assert updated_project.last_sync_hash is not None
        assert updated_project.last_sync_at is not None
        assert isinstance(updated_project.last_sync_hash, str)
        assert len(updated_project.last_sync_hash) == 64

    def test_update_sync_hash_changes_after_file_change(self, db, sample_project, spec_file):
        """Test that update_sync_hash reflects file changes."""
        # Create project and do initial sync
        db.create_project(sample_project)
        update_sync_hash(db, sample_project)

        # Get initial hash
        project1 = db.get_project(sample_project.id)
        initial_hash = project1.last_sync_hash

        # Modify spec file
        spec_file.write_text("""
version: 2
features:
  - id: F001
    title: Modified Feature
    description: Modified
    priority: critical
""")

        # Update sync hash again
        update_sync_hash(db, sample_project)

        # Verify hash changed
        project2 = db.get_project(sample_project.id)
        assert project2.last_sync_hash != initial_hash

    def test_update_sync_hash_sets_timestamp(self, db, sample_project):
        """Test that update_sync_hash sets last_sync_at timestamp."""
        # Create project
        db.create_project(sample_project)

        before = datetime.now()
        update_sync_hash(db, sample_project)
        after = datetime.now()

        # Verify timestamp is within expected range
        updated_project = db.get_project(sample_project.id)
        assert updated_project.last_sync_at is not None
        assert before <= updated_project.last_sync_at <= after


class TestIntegration:
    """Integration tests for sync check workflow."""

    def test_full_sync_check_workflow(self, db, sample_project, spec_file):
        """Test complete workflow: create, sync, check, modify, check again."""
        # 1. Create project - never synced
        db.create_project(sample_project)
        project = db.get_project(sample_project.id)

        # Check should indicate sync needed
        result = check_sync_needed(project)
        assert result.sync_needed is True
        assert result.reason == "Project has never been synced"

        # 2. Simulate sync
        update_sync_hash(db, project)
        project = db.get_project(sample_project.id)

        # Check should indicate no sync needed
        result = check_sync_needed(project)
        assert result.sync_needed is False

        # 3. Modify spec file
        spec_file.write_text("""
version: 2
features:
  - id: F001
    title: Updated
    description: Updated
    priority: high
  - id: F002
    title: New
    description: New
    priority: medium
""")

        # 4. Check should indicate sync needed again
        project = db.get_project(sample_project.id)
        result = check_sync_needed(project)
        assert result.sync_needed is True
        assert result.reason == "Spec source has changed since last sync"

        # 5. Sync again
        update_sync_hash(db, project)
        project = db.get_project(sample_project.id)

        # 6. Check should indicate no sync needed
        result = check_sync_needed(project)
        assert result.sync_needed is False
