"""Tests for F075: Create features in database from parsed spec.

Validates that features parsed from a YAML spec are correctly persisted
to the database with priority, acceptance criteria, and dependencies.
"""

import json
import pathlib
import sqlite3
import textwrap

import pytest
import yaml

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
def project_id(db_path):
    """Create a project and return its ID for use as a foreign key."""
    from bob3.db import create_project

    project = create_project(
        name="Test Project",
        workspace_path="/tmp/test",
    )
    return project.id


# ============================================================
# Step 1: For each feature in spec, create feature record
# ============================================================


class TestCreateFeatureRecords:
    """Step 1: For each feature in spec, create feature record."""

    def test_create_features_from_spec_exists(self):
        """create_features_from_spec function must exist in db module."""
        from bob3.db import create_features_from_spec

        assert callable(create_features_from_spec)

    def test_creates_single_feature(self, db_path, project_id):
        """Creates a single feature from a spec with one feature."""
        from bob3.db import create_features_from_spec, list_features

        spec = {
            "name": "test-project",
            "version": "1.0",
            "features": [
                {"name": "Auth System", "description": "User authentication"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 1
        assert created[0].name == "Auth System"
        assert created[0].description == "User authentication"
        assert created[0].project_id == project_id

    def test_creates_multiple_features(self, db_path, project_id):
        """Creates multiple features from a spec."""
        from bob3.db import create_features_from_spec, list_features

        spec = {
            "name": "test-project",
            "version": "1.0",
            "features": [
                {"name": "Database", "description": "DB layer"},
                {"name": "API", "description": "REST API"},
                {"name": "Frontend", "description": "Web UI"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 3

        features = list_features(project_id=project_id)
        assert len(features) == 3
        names = {f.name for f in features}
        assert names == {"Database", "API", "Frontend"}

    def test_features_persisted_to_database(self, db_path, project_id):
        """Features are actually persisted in the SQLite database."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {"name": "Feature A", "description": "Desc A"},
            ],
        }

        create_features_from_spec(project_id=project_id, spec=spec)

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT name, description FROM features WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            assert row is not None
            assert row[0] == "Feature A"
            assert row[1] == "Desc A"
        finally:
            conn.close()

    def test_handles_string_features(self, db_path, project_id):
        """Handles features listed as plain strings (not dicts)."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": ["Authentication", "Database", "API"],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 3
        assert created[0].name == "Authentication"
        assert created[1].name == "Database"

    def test_handles_empty_features_list(self, db_path, project_id):
        """Returns empty list for spec with no features."""
        from bob3.db import create_features_from_spec

        spec = {"features": []}

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created == []

    def test_handles_missing_features_key(self, db_path, project_id):
        """Returns empty list when spec has no 'features' key."""
        from bob3.db import create_features_from_spec

        spec = {"name": "project", "version": "1.0"}

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created == []

    def test_handles_null_features(self, db_path, project_id):
        """Returns empty list when features is null/None."""
        from bob3.db import create_features_from_spec

        spec = {"features": None}

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created == []

    def test_returns_feature_models(self, db_path, project_id):
        """Returns a list of Feature model instances."""
        from bob3.db import create_features_from_spec
        from bob3.models import Feature

        spec = {
            "features": [
                {"name": "Test", "description": "Test feature"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert all(isinstance(f, Feature) for f in created)


# ============================================================
# Step 2: Set priority from spec
# ============================================================


class TestSetPriorityFromSpec:
    """Step 2: Set priority from spec."""

    def test_priority_set_from_spec(self, db_path, project_id):
        """Feature priority is set from the spec's priority field."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {"name": "High Priority", "description": "Important", "priority": 10},
                {"name": "Low Priority", "description": "Less important", "priority": 90},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created[0].priority == 10
        assert created[1].priority == 90

    def test_default_priority_when_not_specified(self, db_path, project_id):
        """Features without priority get a default based on position."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {"name": "First", "description": "First feature"},
                {"name": "Second", "description": "Second feature"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        # Default priority should be based on index (100, 200, etc.)
        assert created[0].priority < created[1].priority

    def test_priority_preserved_in_database(self, db_path, project_id):
        """Priority is correctly stored in the database."""
        from bob3.db import create_features_from_spec, get_feature

        spec = {
            "features": [
                {"name": "Prioritized", "description": "Has priority", "priority": 42},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        feature = get_feature(created[0].id)
        assert feature is not None
        assert feature.priority == 42


# ============================================================
# Step 3: Extract acceptance criteria
# ============================================================


class TestExtractAcceptanceCriteria:
    """Step 3: Extract acceptance criteria."""

    def test_acceptance_criteria_stored_as_json(self, db_path, project_id):
        """Acceptance criteria from spec are stored as JSON string."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {
                    "name": "Auth",
                    "description": "Authentication",
                    "acceptance_criteria": [
                        "Users can register",
                        "Users can login",
                        "JWT tokens issued",
                    ],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created[0].acceptance_criteria is not None
        criteria = json.loads(created[0].acceptance_criteria)
        assert len(criteria) == 3
        assert "Users can register" in criteria

    def test_acceptance_criteria_none_when_missing(self, db_path, project_id):
        """acceptance_criteria is None when not in spec."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {"name": "Simple", "description": "No criteria"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created[0].acceptance_criteria is None

    def test_acceptance_criteria_persisted(self, db_path, project_id):
        """Acceptance criteria are stored correctly in the database."""
        from bob3.db import create_features_from_spec, get_feature

        spec = {
            "features": [
                {
                    "name": "Tested",
                    "description": "Has criteria",
                    "acceptance_criteria": ["Step 1: Do thing", "Step 2: Verify"],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        feature = get_feature(created[0].id)
        assert feature is not None
        criteria = json.loads(feature.acceptance_criteria)
        assert len(criteria) == 2
        assert "Step 1: Do thing" in criteria

    def test_acceptance_criteria_as_string(self, db_path, project_id):
        """Handles acceptance_criteria given as a single string."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {
                    "name": "StringCriteria",
                    "description": "Has string criteria",
                    "acceptance_criteria": "Must pass all tests",
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert created[0].acceptance_criteria is not None
        criteria = json.loads(created[0].acceptance_criteria)
        assert isinstance(criteria, list)
        assert "Must pass all tests" in criteria


# ============================================================
# Step 4: Create feature dependencies from spec
# ============================================================


class TestCreateFeatureDependencies:
    """Step 4: Create feature dependencies from spec."""

    def test_dependencies_created_from_depends_on(self, db_path, project_id):
        """Dependencies are created when features have depends_on field."""
        from bob3.db import create_features_from_spec, get_feature_dependencies

        spec = {
            "features": [
                {"name": "Core", "description": "Core library", "priority": 10},
                {
                    "name": "API",
                    "description": "REST API",
                    "priority": 20,
                    "depends_on": ["Core"],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        api_feature = next(f for f in created if f.name == "API")
        core_feature = next(f for f in created if f.name == "Core")

        deps = get_feature_dependencies(api_feature.id)
        assert len(deps) == 1
        assert deps[0].depends_on_feature_id == core_feature.id

    def test_multiple_dependencies(self, db_path, project_id):
        """A feature can depend on multiple other features."""
        from bob3.db import create_features_from_spec, get_feature_dependencies

        spec = {
            "features": [
                {"name": "Database", "description": "DB layer", "priority": 10},
                {"name": "Auth", "description": "Auth system", "priority": 20},
                {
                    "name": "API",
                    "description": "REST API",
                    "priority": 30,
                    "depends_on": ["Database", "Auth"],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        api_feature = next(f for f in created if f.name == "API")

        deps = get_feature_dependencies(api_feature.id)
        assert len(deps) == 2
        dep_ids = {d.depends_on_feature_id for d in deps}
        db_feature = next(f for f in created if f.name == "Database")
        auth_feature = next(f for f in created if f.name == "Auth")
        assert db_feature.id in dep_ids
        assert auth_feature.id in dep_ids

    def test_no_dependencies_when_not_specified(self, db_path, project_id):
        """Features without depends_on have no dependencies."""
        from bob3.db import create_features_from_spec, get_feature_dependencies

        spec = {
            "features": [
                {"name": "Standalone", "description": "No deps"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        deps = get_feature_dependencies(created[0].id)
        assert deps == []

    def test_unknown_dependency_ignored(self, db_path, project_id):
        """Dependencies referencing unknown feature names are skipped gracefully."""
        from bob3.db import create_features_from_spec, get_feature_dependencies

        spec = {
            "features": [
                {"name": "Core", "description": "Core library", "priority": 10},
                {
                    "name": "API",
                    "description": "REST API",
                    "priority": 20,
                    "depends_on": ["Core", "NonexistentFeature"],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        api_feature = next(f for f in created if f.name == "API")

        deps = get_feature_dependencies(api_feature.id)
        # Only the valid dependency should be created
        assert len(deps) == 1


# ============================================================
# Step 5: Test: Plan from spec with 5 features, verify all created in DB
# ============================================================


class TestPlanFromSpecFiveFeatures:
    """Step 5: Integration test - plan from spec with 5 features, verify all in DB."""

    def test_five_features_created_in_database(self, db_path, project_id):
        """Create 5 features from spec and verify all are in the database."""
        from bob3.db import create_features_from_spec, list_features

        spec = {
            "name": "big-project",
            "version": "2.0",
            "features": [
                {
                    "name": "Database Schema",
                    "description": "Create SQLite database",
                    "priority": 10,
                    "acceptance_criteria": ["Create tables", "Add indexes"],
                },
                {
                    "name": "Data Models",
                    "description": "Pydantic models",
                    "priority": 20,
                    "acceptance_criteria": ["Model validation", "Type hints"],
                    "depends_on": ["Database Schema"],
                },
                {
                    "name": "CLI Interface",
                    "description": "Click CLI",
                    "priority": 30,
                    "acceptance_criteria": ["init command", "plan command", "run command"],
                },
                {
                    "name": "Orchestrator",
                    "description": "Build orchestration loop",
                    "priority": 40,
                    "depends_on": ["Data Models", "CLI Interface"],
                },
                {
                    "name": "Test Suite",
                    "description": "Comprehensive tests",
                    "priority": 50,
                    "acceptance_criteria": ["Unit tests", "Integration tests"],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 5

        # Verify all features are in the database
        features = list_features(project_id=project_id)
        assert len(features) == 5

        # Verify ordering by priority
        names_by_priority = [f.name for f in features]
        assert names_by_priority == [
            "Database Schema",
            "Data Models",
            "CLI Interface",
            "Orchestrator",
            "Test Suite",
        ]

    def test_five_features_with_correct_priorities(self, db_path, project_id):
        """All 5 features have their correct priorities from spec."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {"name": "F1", "description": "First", "priority": 10},
                {"name": "F2", "description": "Second", "priority": 20},
                {"name": "F3", "description": "Third", "priority": 30},
                {"name": "F4", "description": "Fourth", "priority": 40},
                {"name": "F5", "description": "Fifth", "priority": 50},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        for i, feature in enumerate(created):
            assert feature.priority == (i + 1) * 10

    def test_five_features_with_acceptance_criteria(self, db_path, project_id):
        """All 5 features have their acceptance criteria stored."""
        from bob3.db import create_features_from_spec

        spec = {
            "features": [
                {
                    "name": f"Feature {i}",
                    "description": f"Feature {i} desc",
                    "priority": i * 10,
                    "acceptance_criteria": [f"Criterion {i}.1", f"Criterion {i}.2"],
                }
                for i in range(1, 6)
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 5
        for i, feature in enumerate(created):
            criteria = json.loads(feature.acceptance_criteria)
            assert len(criteria) == 2
            assert f"Criterion {i + 1}.1" in criteria

    def test_five_features_with_dependencies(self, db_path, project_id):
        """Dependencies between 5 features are correctly created."""
        from bob3.db import create_features_from_spec, get_feature_dependencies

        spec = {
            "features": [
                {"name": "Base", "description": "Base", "priority": 10},
                {
                    "name": "Layer1",
                    "description": "Layer 1",
                    "priority": 20,
                    "depends_on": ["Base"],
                },
                {
                    "name": "Layer2",
                    "description": "Layer 2",
                    "priority": 30,
                    "depends_on": ["Base"],
                },
                {
                    "name": "Integration",
                    "description": "Integration",
                    "priority": 40,
                    "depends_on": ["Layer1", "Layer2"],
                },
                {
                    "name": "Tests",
                    "description": "Tests",
                    "priority": 50,
                    "depends_on": ["Integration"],
                },
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        name_to_id = {f.name: f.id for f in created}

        # Base has no deps
        assert get_feature_dependencies(name_to_id["Base"]) == []

        # Layer1 depends on Base
        deps = get_feature_dependencies(name_to_id["Layer1"])
        assert len(deps) == 1
        assert deps[0].depends_on_feature_id == name_to_id["Base"]

        # Integration depends on Layer1 and Layer2
        deps = get_feature_dependencies(name_to_id["Integration"])
        assert len(deps) == 2
        dep_ids = {d.depends_on_feature_id for d in deps}
        assert name_to_id["Layer1"] in dep_ids
        assert name_to_id["Layer2"] in dep_ids

        # Tests depends on Integration
        deps = get_feature_dependencies(name_to_id["Tests"])
        assert len(deps) == 1
        assert deps[0].depends_on_feature_id == name_to_id["Integration"]

    def test_plan_command_creates_features_in_db(self, db_path):
        """Integration: plan command with --create creates features in DB."""
        from bob3.cli import main
        from bob3.db import create_project, list_features

        # Create a project first
        project = create_project(
            name="CLI Test Project",
            workspace_path="/tmp/cli-test",
        )

        from click.testing import CliRunner

        spec_content = textwrap.dedent("""\
            name: CLI Test Project
            version: "1.0"
            features:
              - name: Auth
                description: User authentication
                priority: 10
                acceptance_criteria:
                  - Login works
                  - Register works
              - name: Database
                description: SQLite DB layer
                priority: 20
              - name: API
                description: REST API
                priority: 30
                depends_on:
                  - Auth
                  - Database
              - name: Frontend
                description: Web interface
                priority: 40
              - name: Tests
                description: Test suite
                priority: 50
        """)

        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(spec_content)
            spec_path = f.name

        runner = CliRunner()
        result = runner.invoke(main, ["plan", spec_path, "--create"])
        assert result.exit_code == 0, f"Plan command failed: {result.output}"

        features = list_features(project_id=project.id)
        assert len(features) == 5

        import os

        os.unlink(spec_path)
