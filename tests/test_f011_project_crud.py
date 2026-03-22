"""Tests for F011: Database CRUD operations for projects table."""

import pathlib
import sqlite3
from datetime import datetime

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


class TestCreateProject:
    """Step 1: create_project() inserts a new project and returns it."""

    def test_create_project_returns_project_model(self, db_path):
        from bob3.db import create_project
        from bob3.models import Project

        project = create_project(
            name="Test Project",
            workspace_path="/tmp/test",
        )
        assert isinstance(project, Project)

    def test_create_project_sets_id(self, db_path):
        from bob3.db import create_project

        project = create_project(
            name="Test Project",
            workspace_path="/tmp/test",
        )
        assert project.id is not None
        assert len(project.id) > 0

    def test_create_project_persists_to_database(self, db_path):
        from bob3.db import create_project

        project = create_project(
            name="Persisted Project",
            workspace_path="/tmp/persist",
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name, workspace_path FROM projects WHERE id = ?",
                (project.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "Persisted Project"
            assert row[1] == "/tmp/persist"
        finally:
            conn.close()

    def test_create_project_with_optional_fields(self, db_path):
        from bob3.db import create_project

        project = create_project(
            name="Full Project",
            workspace_path="/tmp/full",
            description="A full project",
            spec_path="/tmp/spec.yaml",
            max_cost_usd=100.0,
        )
        assert project.description == "A full project"
        assert project.spec_path == "/tmp/spec.yaml"
        assert project.max_cost_usd == 100.0

    def test_create_project_default_status_is_planning(self, db_path):
        from bob3.db import create_project

        project = create_project(
            name="New Project",
            workspace_path="/tmp/new",
        )
        assert project.status == "planning"

    def test_create_project_default_costs(self, db_path):
        from bob3.db import create_project

        project = create_project(
            name="Cost Project",
            workspace_path="/tmp/cost",
        )
        assert project.total_cost_usd == 0.0
        assert project.max_cost_usd == 500.0

    def test_create_project_sets_timestamps(self, db_path):
        from bob3.db import create_project

        project = create_project(
            name="Timestamp Project",
            workspace_path="/tmp/ts",
        )
        assert project.created_at is not None
        assert project.updated_at is not None

    def test_create_project_duplicate_name_allowed(self, db_path):
        from bob3.db import create_project

        p1 = create_project(name="Same Name", workspace_path="/tmp/a")
        p2 = create_project(name="Same Name", workspace_path="/tmp/b")
        assert p1.id != p2.id


class TestGetProject:
    """Step 2: get_project() retrieves a project by ID."""

    def test_get_project_returns_project(self, db_path):
        from bob3.db import create_project, get_project
        from bob3.models import Project

        created = create_project(name="Get Me", workspace_path="/tmp/get")
        fetched = get_project(created.id)
        assert isinstance(fetched, Project)

    def test_get_project_has_correct_fields(self, db_path):
        from bob3.db import create_project, get_project

        created = create_project(
            name="Detail Project",
            workspace_path="/tmp/detail",
            description="Some description",
            spec_path="/tmp/spec.yaml",
        )
        fetched = get_project(created.id)
        assert fetched.name == "Detail Project"
        assert fetched.workspace_path == "/tmp/detail"
        assert fetched.description == "Some description"
        assert fetched.spec_path == "/tmp/spec.yaml"

    def test_get_project_not_found_returns_none(self, db_path):
        from bob3.db import get_project

        result = get_project("nonexistent-id")
        assert result is None

    def test_get_project_preserves_id(self, db_path):
        from bob3.db import create_project, get_project

        created = create_project(name="ID Test", workspace_path="/tmp/id")
        fetched = get_project(created.id)
        assert fetched.id == created.id


class TestUpdateProject:
    """Step 3: update_project() modifies existing project fields."""

    def test_update_project_changes_name(self, db_path):
        from bob3.db import create_project, get_project, update_project

        project = create_project(name="Old Name", workspace_path="/tmp/up")
        update_project(project.id, name="New Name")
        fetched = get_project(project.id)
        assert fetched.name == "New Name"

    def test_update_project_changes_status(self, db_path):
        from bob3.db import create_project, get_project, update_project

        project = create_project(name="Status Test", workspace_path="/tmp/st")
        update_project(project.id, status="executing")
        fetched = get_project(project.id)
        assert fetched.status == "executing"

    def test_update_project_changes_description(self, db_path):
        from bob3.db import create_project, get_project, update_project

        project = create_project(name="Desc Test", workspace_path="/tmp/desc")
        update_project(project.id, description="Updated description")
        fetched = get_project(project.id)
        assert fetched.description == "Updated description"

    def test_update_project_changes_cost(self, db_path):
        from bob3.db import create_project, get_project, update_project

        project = create_project(name="Cost Test", workspace_path="/tmp/cost")
        update_project(project.id, total_cost_usd=42.5)
        fetched = get_project(project.id)
        assert fetched.total_cost_usd == 42.5

    def test_update_project_returns_updated_project(self, db_path):
        from bob3.db import create_project, update_project
        from bob3.models import Project

        project = create_project(name="Return Test", workspace_path="/tmp/ret")
        updated = update_project(project.id, name="Updated")
        assert isinstance(updated, Project)
        assert updated.name == "Updated"

    def test_update_project_not_found_returns_none(self, db_path):
        from bob3.db import update_project

        result = update_project("nonexistent-id", name="Ghost")
        assert result is None

    def test_update_project_updates_timestamp(self, db_path):
        from bob3.db import create_project, get_project, update_project
        import time

        project = create_project(name="TS Test", workspace_path="/tmp/ts")
        original_updated = project.updated_at
        time.sleep(0.05)
        update_project(project.id, name="TS Updated")
        fetched = get_project(project.id)
        assert fetched.updated_at >= original_updated

    def test_update_project_multiple_fields(self, db_path):
        from bob3.db import create_project, get_project, update_project

        project = create_project(name="Multi Test", workspace_path="/tmp/multi")
        update_project(
            project.id,
            name="Multi Updated",
            status="completed",
            description="Done",
        )
        fetched = get_project(project.id)
        assert fetched.name == "Multi Updated"
        assert fetched.status == "completed"
        assert fetched.description == "Done"

    def test_update_project_no_fields_is_noop(self, db_path):
        from bob3.db import create_project, get_project, update_project

        project = create_project(name="Noop Test", workspace_path="/tmp/noop")
        updated = update_project(project.id)
        fetched = get_project(project.id)
        assert fetched.name == "Noop Test"


class TestListProjects:
    """Step 4: list_projects() returns all projects."""

    def test_list_projects_empty(self, db_path):
        from bob3.db import list_projects

        projects = list_projects()
        assert projects == []

    def test_list_projects_returns_all(self, db_path):
        from bob3.db import create_project, list_projects

        create_project(name="Project A", workspace_path="/tmp/a")
        create_project(name="Project B", workspace_path="/tmp/b")
        create_project(name="Project C", workspace_path="/tmp/c")

        projects = list_projects()
        assert len(projects) == 3
        names = {p.name for p in projects}
        assert names == {"Project A", "Project B", "Project C"}

    def test_list_projects_returns_project_models(self, db_path):
        from bob3.db import create_project, list_projects
        from bob3.models import Project

        create_project(name="Model Test", workspace_path="/tmp/model")
        projects = list_projects()
        assert all(isinstance(p, Project) for p in projects)

    def test_list_projects_after_update(self, db_path):
        from bob3.db import create_project, update_project, list_projects

        project = create_project(name="Before", workspace_path="/tmp/before")
        update_project(project.id, name="After")
        projects = list_projects()
        assert len(projects) == 1
        assert projects[0].name == "After"


class TestTransactionsAndErrorHandling:
    """Step 5-6: Verify transaction behavior and error handling."""

    def test_create_project_with_missing_required_field_raises(self, db_path):
        from bob3.db import create_project

        with pytest.raises((TypeError, Exception)):
            create_project(name="No Workspace")  # Missing workspace_path

    def test_concurrent_creates_unique_ids(self, db_path):
        from bob3.db import create_project

        projects = [
            create_project(name=f"Project {i}", workspace_path=f"/tmp/{i}")
            for i in range(10)
        ]
        ids = [p.id for p in projects]
        assert len(set(ids)) == 10  # All unique
