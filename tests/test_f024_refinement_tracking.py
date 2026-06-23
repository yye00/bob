"""Tests for F024: Feature refinement tracking and max attempts enforcement.

Validates that:
- increment_refinement_attempts() increments the counter atomically
- check_refinement_limit() returns correct True/False based on limit
- Refining 5 times then checking the 6th triggers needs_human status
- refinement_attempts counter updates correctly in the database
"""

import pathlib
import tempfile

import pytest

from bob3.db import (
    check_refinement_limit,
    connect,
    create_feature,
    create_project,
    get_feature,
    increment_refinement_attempts,
    init_database,
)


@pytest.fixture
def db_path():
    """Provide a temporary database path and initialize the schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir) / "test.db"
        init_database(db_path=path)
        yield path


@pytest.fixture
def project(db_path, monkeypatch):
    """Create a test project and patch the database path."""
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    return create_project(
        name="Test Project",
        workspace_path="/tmp/test_project",
    )


@pytest.fixture
def feature(project, db_path, monkeypatch):
    """Create a test feature with default max_refinement_attempts=5."""
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    return create_feature(
        project_id=project.id,
        name="Test Feature",
        description="A feature for testing refinement tracking",
        status="refining",
    )


class TestIncrementRefinementAttempts:
    """Tests for the increment_refinement_attempts() function."""

    def test_increment_from_zero(self, feature, db_path, monkeypatch):
        """Incrementing from 0 should set refinement_attempts to 1."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        updated = increment_refinement_attempts(feature.id)
        assert updated is not None
        assert updated.refinement_attempts == 1

    def test_increment_multiple_times(self, feature, db_path, monkeypatch):
        """Incrementing multiple times should increment by 1 each time."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        for i in range(1, 4):
            updated = increment_refinement_attempts(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == i

    def test_increment_nonexistent_feature(self, db_path, monkeypatch):
        """Incrementing a nonexistent feature should return None."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        result = increment_refinement_attempts("nonexistent-id")
        assert result is None

    def test_increment_updates_database(self, feature, db_path, monkeypatch):
        """The increment should persist to the database."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        increment_refinement_attempts(feature.id)
        increment_refinement_attempts(feature.id)
        fetched = get_feature(feature.id)
        assert fetched is not None
        assert fetched.refinement_attempts == 2

    def test_increment_updates_updated_at(self, feature, db_path, monkeypatch):
        """The increment should update the updated_at timestamp."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        original_updated_at = feature.updated_at
        updated = increment_refinement_attempts(feature.id)
        assert updated is not None
        assert updated.updated_at >= original_updated_at

    def test_increment_at_limit_sets_needs_human(self, feature, db_path, monkeypatch):
        """When incrementing reaches max_refinement_attempts, status should become needs_human."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        # Feature has max_refinement_attempts=5, increment 5 times
        for _ in range(4):
            updated = increment_refinement_attempts(feature.id)
            assert updated is not None
            assert updated.status != "needs_human"
        # 5th increment should trigger needs_human
        updated = increment_refinement_attempts(feature.id)
        assert updated is not None
        assert updated.refinement_attempts == 5
        assert updated.status == "needs_human"

    def test_increment_past_limit_keeps_needs_human(self, feature, db_path, monkeypatch):
        """Incrementing past the limit should still keep needs_human status."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        for _ in range(6):
            increment_refinement_attempts(feature.id)
        fetched = get_feature(feature.id)
        assert fetched is not None
        assert fetched.status == "needs_human"
        assert fetched.refinement_attempts == 6


class TestCheckRefinementLimit:
    """Tests for the check_refinement_limit() function."""

    def test_under_limit(self, feature, db_path, monkeypatch):
        """Feature with 0 attempts should not be at the limit."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        result = check_refinement_limit(feature.id)
        assert result is False

    def test_at_limit(self, feature, db_path, monkeypatch):
        """Feature with attempts == max should be at the limit."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        for _ in range(5):
            increment_refinement_attempts(feature.id)
        result = check_refinement_limit(feature.id)
        assert result is True

    def test_over_limit(self, feature, db_path, monkeypatch):
        """Feature with attempts > max should be at the limit."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        for _ in range(7):
            increment_refinement_attempts(feature.id)
        result = check_refinement_limit(feature.id)
        assert result is True

    def test_nonexistent_feature(self, db_path, monkeypatch):
        """Checking a nonexistent feature should return None."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        result = check_refinement_limit("nonexistent-id")
        assert result is None

    def test_custom_max_attempts(self, project, db_path, monkeypatch):
        """Feature with custom max_refinement_attempts should use that value."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        from bob3.db import update_feature
        feat = create_feature(
            project_id=project.id,
            name="Custom Max Feature",
            status="refining",
        )
        update_feature(feat.id, max_refinement_attempts=3)
        for _ in range(2):
            increment_refinement_attempts(feat.id)
        assert check_refinement_limit(feat.id) is False
        increment_refinement_attempts(feat.id)
        assert check_refinement_limit(feat.id) is True


class TestRefinementFullCycle:
    """Integration tests for the full refinement cycle as per acceptance criteria."""

    def test_refine_5_times_6th_triggers_needs_human(self, feature, db_path, monkeypatch):
        """Step 3: Refine feature 5 times, verify 6th attempt triggers needs_human.

        The acceptance criterion says the 6th attempt should trigger needs_human.
        With max_refinement_attempts=5, the 5th increment reaches the limit.
        The check_refinement_limit on the 6th attempt confirms the limit is exceeded.
        """
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        # Refine 5 times
        for i in range(5):
            updated = increment_refinement_attempts(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == i + 1

        # After 5 refinements, the feature should be at needs_human
        fetched = get_feature(feature.id)
        assert fetched is not None
        assert fetched.status == "needs_human"
        assert fetched.refinement_attempts == 5

        # The 6th check should confirm the limit is reached
        assert check_refinement_limit(feature.id) is True

    def test_counter_updates_correctly(self, feature, db_path, monkeypatch):
        """Step 4: Verify refinement_attempts counter updates correctly."""
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
        for expected in range(1, 6):
            updated = increment_refinement_attempts(feature.id)
            assert updated is not None
            assert updated.refinement_attempts == expected
            # Also verify via direct database read
            fetched = get_feature(feature.id)
            assert fetched is not None
            assert fetched.refinement_attempts == expected
