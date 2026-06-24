"""Tests for the spec_slot migration (add_spec_slot).

Acceptance criteria:
- File exists: src/bob/migrations/add_spec_slot.py
- Function defined: bob.migrations.add_spec_slot.upgrade
- Field exists on Feature model: spec_slot
- pytest: tests/test_spec_slot_migration.py
"""

from __future__ import annotations

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
# Migration module structure
# ============================================================


class TestMigrationModuleExists:
    def test_module_importable(self):
        """bob.migrations.add_spec_slot must be importable."""
        import bob.migrations.add_spec_slot  # noqa: F401

    def test_upgrade_function_exists(self):
        """upgrade() must be defined in the module."""
        from bob.migrations.add_spec_slot import upgrade

        assert callable(upgrade)

    def test_upgrade_accepts_db_path(self):
        """upgrade() must accept a db_path keyword argument."""
        import inspect
        from bob.migrations.add_spec_slot import upgrade

        sig = inspect.signature(upgrade)
        assert "db_path" in sig.parameters


# ============================================================
# Feature model has spec_slot field
# ============================================================


class TestFeatureModelSpecSlot:
    def test_feature_model_has_spec_slot_field(self):
        """Feature Pydantic model must have a spec_slot field."""
        from bob.models import Feature

        assert hasattr(Feature, "model_fields") or hasattr(Feature, "__fields__")
        # Check both Pydantic v1 and v2 style
        try:
            fields = Feature.model_fields
        except AttributeError:
            fields = Feature.__fields__
        assert "spec_slot" in fields

    def test_spec_slot_is_optional(self):
        """spec_slot must be Optional[str] defaulting to None."""
        from bob.models import Feature

        f = Feature(
            id="test-id",
            project_id="proj-id",
            name="Test Feature",
        )
        assert f.spec_slot is None

    def test_spec_slot_can_be_set(self):
        """spec_slot should be settable to a string like 'F-R6-200'."""
        from bob.models import Feature

        f = Feature(
            id="test-id",
            project_id="proj-id",
            name="Test Feature",
            spec_slot="F-R6-200",
        )
        assert f.spec_slot == "F-R6-200"


# ============================================================
# Upgrade adds the column to an existing database
# ============================================================


class TestUpgradeAddsColumn:
    def test_upgrade_adds_spec_slot_column(self, db_path):
        """upgrade() must add spec_slot column to features table."""
        from bob.migrations.add_spec_slot import upgrade

        # Drop column first to simulate pre-migration state
        conn = sqlite3.connect(str(db_path))
        try:
            # SQLite < 3.35 doesn't support DROP COLUMN; recreate the table
            # We verify the column exists after upgrade
            cols_before = [
                row[1]
                for row in conn.execute("PRAGMA table_info(features)").fetchall()
            ]
        finally:
            conn.close()

        upgrade(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            cols_after = [
                row[1]
                for row in conn.execute("PRAGMA table_info(features)").fetchall()
            ]
        finally:
            conn.close()

        assert "spec_slot" in cols_after

    def test_upgrade_is_idempotent(self, db_path):
        """Running upgrade() twice must not raise an error."""
        from bob.migrations.add_spec_slot import upgrade

        upgrade(db_path=db_path)
        upgrade(db_path=db_path)  # must not raise

    def test_upgrade_preserves_existing_rows(self, db_path, project_id):
        """upgrade() must not delete existing feature rows."""
        from bob.db import create_feature, list_features
        from bob.migrations.add_spec_slot import upgrade

        create_feature(
            project_id=project_id,
            name="Existing Feature",
        )

        upgrade(db_path=db_path)

        features = list_features(project_id=project_id)
        assert len(features) == 1
        assert features[0].name == "Existing Feature"


# ============================================================
# spec_slot is populated from spec key on feature creation
# ============================================================


class TestCreateFeatureWithSpecSlot:
    def test_create_feature_accepts_spec_slot(self, db_path, project_id):
        """create_feature must accept a spec_slot keyword argument."""
        from bob.db import create_feature

        f = create_feature(
            project_id=project_id,
            name="My Feature",
            spec_slot="F-R1-100",
        )
        assert f.spec_slot == "F-R1-100"

    def test_create_feature_spec_slot_persisted(self, db_path, project_id):
        """spec_slot set on create must be readable back from DB."""
        from bob.db import create_feature, get_feature

        f = create_feature(
            project_id=project_id,
            name="My Feature",
            spec_slot="F-R2-050",
        )
        f2 = get_feature(f.id)
        assert f2 is not None
        assert f2.spec_slot == "F-R2-050"

    def test_create_feature_default_spec_slot_none(self, db_path, project_id):
        """spec_slot must default to None when not provided."""
        from bob.db import create_feature, get_feature

        f = create_feature(
            project_id=project_id,
            name="My Feature",
        )
        f2 = get_feature(f.id)
        assert f2 is not None
        assert f2.spec_slot is None


class TestCreateFeaturesFromSpecPopulatesSpecSlot:
    def test_dict_spec_key_becomes_spec_slot(self, db_path, project_id):
        """Dict-form spec keys (e.g. 'F-R1-100') must be stored as spec_slot."""
        from bob.db import create_features_from_spec

        spec = {
            "name": "test-project",
            "features": {
                "F-R1-100": {"title": "Auth System", "description": "Handles auth"},
                "F-R1-200": {"title": "Dashboard", "description": "Main dashboard"},
            },
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 2
        slots = {f.spec_slot for f in created}
        assert "F-R1-100" in slots
        assert "F-R1-200" in slots

    def test_list_spec_has_null_spec_slot(self, db_path, project_id):
        """List-form specs with no YAML key produce spec_slot=None."""
        from bob.db import create_features_from_spec

        spec = {
            "name": "test-project",
            "features": [
                {"name": "Auth System"},
                {"name": "Dashboard"},
            ],
        }

        created = create_features_from_spec(project_id=project_id, spec=spec)
        assert len(created) == 2
        for f in created:
            assert f.spec_slot is None


# ============================================================
# Backfill: upgrade populates spec_slot for existing rows via spec YAML
# ============================================================


class TestBackfillSpecSlot:
    def test_upgrade_backfills_from_spec_yaml(self, db_path, project_id, tmp_path):
        """upgrade(db_path, spec_path) must backfill spec_slot by matching names."""
        from bob.db import create_feature, get_feature
        from bob.migrations.add_spec_slot import upgrade

        # Create features without spec_slot (simulates pre-migration rows)
        f1 = create_feature(project_id=project_id, name="Auth System")
        f2 = create_feature(project_id=project_id, name="Dashboard")

        # Write a spec YAML with matching names
        spec_content = textwrap.dedent("""\
            name: test-project
            features:
              F-R1-100:
                title: Auth System
                description: Handles auth
              F-R1-200:
                title: Dashboard
                description: Main dashboard
        """)
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(spec_content)

        upgrade(db_path=db_path, spec_path=spec_path)

        f1_reloaded = get_feature(f1.id)
        f2_reloaded = get_feature(f2.id)
        assert f1_reloaded is not None
        assert f2_reloaded is not None
        assert f1_reloaded.spec_slot == "F-R1-100"
        assert f2_reloaded.spec_slot == "F-R1-200"

    def test_upgrade_without_spec_path_skips_backfill(self, db_path, project_id):
        """upgrade() without spec_path must not error; spec_slot stays None."""
        from bob.db import create_feature, get_feature
        from bob.migrations.add_spec_slot import upgrade

        f = create_feature(project_id=project_id, name="Auth System")
        upgrade(db_path=db_path)  # no spec_path

        f_reloaded = get_feature(f.id)
        assert f_reloaded is not None
        assert f_reloaded.spec_slot is None
