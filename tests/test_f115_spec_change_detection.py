"""Tests for F115: Spec Change Detection.

Detects when the app_spec.yaml has changed since last run.
Computes and stores SHA256 hash of spec file, compares on run,
identifies new/modified/removed features, and updates the database.
"""

import json
import pathlib

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
def spec_file(tmp_path):
    """Create a sample YAML spec file."""
    spec = {
        "name": "TestProject",
        "version": "1.0",
        "features": [
            {
                "name": "Feature A",
                "description": "First feature",
                "priority": 10,
                "acceptance_criteria": ["Step 1: Do thing A"],
            },
            {
                "name": "Feature B",
                "description": "Second feature",
                "priority": 20,
                "acceptance_criteria": ["Step 1: Do thing B"],
            },
        ],
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.dump(spec, default_flow_style=False))
    return spec_path


@pytest.fixture()
def project_with_spec(db_path, spec_file):
    """Create a project with features loaded from spec."""
    from bob.db import create_feature, create_project

    project = create_project(
        name="TestProject",
        workspace_path="/tmp/test",
        spec_path=str(spec_file),
    )
    # Create features matching the spec
    create_feature(
        project_id=project.id,
        name="Feature A",
        description="First feature",
        priority=10,
        acceptance_criteria=json.dumps(["Step 1: Do thing A"]),
    )
    create_feature(
        project_id=project.id,
        name="Feature B",
        description="Second feature",
        priority=20,
        acceptance_criteria=json.dumps(["Step 1: Do thing B"]),
    )
    return project


# ============================================================
# Step 2: compute_spec_hash(spec_path) -> SHA256
# ============================================================


class TestComputeSpecHash:
    """Step 2: compute_spec_hash returns SHA256 hex digest of spec file."""

    def test_returns_sha256_hex_string(self, spec_file):
        from bob.db import compute_spec_hash

        result = compute_spec_hash(spec_file)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest is 64 chars

    def test_same_content_produces_same_hash(self, spec_file):
        from bob.db import compute_spec_hash

        hash1 = compute_spec_hash(spec_file)
        hash2 = compute_spec_hash(spec_file)
        assert hash1 == hash2

    def test_different_content_produces_different_hash(self, tmp_path):
        from bob.db import compute_spec_hash

        spec_a = tmp_path / "a.yaml"
        spec_b = tmp_path / "b.yaml"
        spec_a.write_text("name: Alpha\n")
        spec_b.write_text("name: Beta\n")

        assert compute_spec_hash(spec_a) != compute_spec_hash(spec_b)

    def test_nonexistent_file_raises(self, tmp_path):
        from bob.db import compute_spec_hash

        with pytest.raises(FileNotFoundError):
            compute_spec_hash(tmp_path / "nonexistent.yaml")


# ============================================================
# Step 3: Store spec_hash on bob plan
# ============================================================


class TestStoreSpecHash:
    """Step 3: Storing spec hash on project via update_project."""

    def test_store_spec_hash_on_project(self, db_path, spec_file):
        from bob.db import compute_spec_hash, create_project, get_project, update_project

        project = create_project(
            name="HashTest",
            workspace_path="/tmp/hash",
            spec_path=str(spec_file),
        )
        spec_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=spec_hash)

        fetched = get_project(project.id)
        assert fetched.spec_hash == spec_hash

    def test_spec_hash_initially_none(self, db_path):
        from bob.db import create_project

        project = create_project(
            name="NoHash",
            workspace_path="/tmp/nohash",
        )
        assert project.spec_hash is None


# ============================================================
# Step 4: On bob run, compare current hash with stored hash
# ============================================================


class TestCheckSpecChanged:
    """Step 4: check_spec_changed compares current hash with stored hash."""

    def test_returns_false_when_no_change(self, db_path, spec_file):
        from bob.db import (
            check_spec_changed,
            compute_spec_hash,
            create_project,
            update_project,
        )

        project = create_project(
            name="NoChange",
            workspace_path="/tmp/nc",
            spec_path=str(spec_file),
        )
        spec_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=spec_hash)

        changed, old_hash, new_hash = check_spec_changed(project.id)
        assert changed is False
        assert old_hash == new_hash

    def test_returns_true_when_spec_changed(self, db_path, spec_file):
        from bob.db import (
            check_spec_changed,
            compute_spec_hash,
            create_project,
            update_project,
        )

        project = create_project(
            name="Changed",
            workspace_path="/tmp/chg",
            spec_path=str(spec_file),
        )
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        # Modify the spec file
        spec_file.write_text(yaml.dump({"name": "Modified", "features": []}))

        changed, returned_old, returned_new = check_spec_changed(project.id)
        assert changed is True
        assert returned_old == old_hash
        assert returned_new != old_hash

    def test_returns_true_when_no_stored_hash(self, db_path, spec_file):
        from bob.db import check_spec_changed, create_project

        project = create_project(
            name="NoStored",
            workspace_path="/tmp/nos",
            spec_path=str(spec_file),
        )
        # No spec_hash set on project
        changed, old_hash, new_hash = check_spec_changed(project.id)
        assert changed is True
        assert old_hash is None
        assert new_hash is not None

    def test_returns_false_when_no_spec_path(self, db_path):
        from bob.db import check_spec_changed, create_project

        project = create_project(
            name="NoSpec",
            workspace_path="/tmp/nospec",
        )
        changed, old_hash, new_hash = check_spec_changed(project.id)
        assert changed is False
        assert old_hash is None
        assert new_hash is None


# ============================================================
# Step 6: diff_features() to identify added/modified/removed features
# ============================================================


class TestDiffFeatures:
    """Step 6: diff_features identifies added, modified, and removed features."""

    def test_no_changes(self):
        from bob.db import diff_features

        old = [
            {"name": "A", "description": "desc A", "priority": 10},
            {"name": "B", "description": "desc B", "priority": 20},
        ]
        new = [
            {"name": "A", "description": "desc A", "priority": 10},
            {"name": "B", "description": "desc B", "priority": 20},
        ]
        result = diff_features(old, new)
        assert result["added"] == []
        assert result["modified"] == []
        assert result["removed"] == []

    def test_added_features(self):
        from bob.db import diff_features

        old = [{"name": "A", "description": "desc A"}]
        new = [
            {"name": "A", "description": "desc A"},
            {"name": "C", "description": "desc C"},
        ]
        result = diff_features(old, new)
        assert len(result["added"]) == 1
        assert result["added"][0]["name"] == "C"
        assert result["modified"] == []
        assert result["removed"] == []

    def test_removed_features(self):
        from bob.db import diff_features

        old = [
            {"name": "A", "description": "desc A"},
            {"name": "B", "description": "desc B"},
        ]
        new = [{"name": "A", "description": "desc A"}]
        result = diff_features(old, new)
        assert result["added"] == []
        assert result["modified"] == []
        assert len(result["removed"]) == 1
        assert result["removed"][0]["name"] == "B"

    def test_modified_features(self):
        from bob.db import diff_features

        old = [{"name": "A", "description": "old desc", "priority": 10}]
        new = [{"name": "A", "description": "new desc", "priority": 10}]
        result = diff_features(old, new)
        assert result["added"] == []
        assert len(result["modified"]) == 1
        assert result["modified"][0]["name"] == "A"
        assert result["removed"] == []

    def test_mixed_changes(self):
        from bob.db import diff_features

        old = [
            {"name": "A", "description": "desc A"},
            {"name": "B", "description": "old B"},
            {"name": "C", "description": "desc C"},
        ]
        new = [
            {"name": "A", "description": "desc A"},
            {"name": "B", "description": "new B"},
            {"name": "D", "description": "desc D"},
        ]
        result = diff_features(old, new)
        assert len(result["added"]) == 1
        assert result["added"][0]["name"] == "D"
        assert len(result["modified"]) == 1
        assert result["modified"][0]["name"] == "B"
        assert len(result["removed"]) == 1
        assert result["removed"][0]["name"] == "C"

    def test_empty_old_all_added(self):
        from bob.db import diff_features

        old = []
        new = [{"name": "X", "description": "new"}]
        result = diff_features(old, new)
        assert len(result["added"]) == 1
        assert result["removed"] == []
        assert result["modified"] == []

    def test_empty_new_all_removed(self):
        from bob.db import diff_features

        old = [{"name": "X", "description": "old"}]
        new = []
        result = diff_features(old, new)
        assert result["added"] == []
        assert result["modified"] == []
        assert len(result["removed"]) == 1


# ============================================================
# Step 5 & 7: detect_spec_changes applies changes to database
# ============================================================


class TestDetectSpecChanges:
    """Steps 5 & 7: detect_spec_changes re-parses spec and updates DB."""

    def test_detect_new_feature_adds_to_db(self, db_path, spec_file, project_with_spec):
        from bob.db import compute_spec_hash, detect_spec_changes, list_features, update_project

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        # Add a new feature to spec
        spec = yaml.safe_load(spec_file.read_text())
        spec["features"].append({
            "name": "Feature C",
            "description": "Third feature",
            "priority": 30,
            "acceptance_criteria": ["Step 1: Do thing C"],
        })
        spec_file.write_text(yaml.dump(spec, default_flow_style=False))

        changes = detect_spec_changes(project.id)
        assert len(changes["added"]) == 1
        assert changes["added"][0]["name"] == "Feature C"

        # Verify feature was added to DB
        features = list_features(project_id=project.id)
        names = {f.name for f in features}
        assert "Feature C" in names

    def test_detect_removed_feature_marks_removed(self, db_path, spec_file, project_with_spec):
        from bob.db import compute_spec_hash, detect_spec_changes, list_features, update_project

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        # Remove Feature B from spec
        spec = yaml.safe_load(spec_file.read_text())
        spec["features"] = [f for f in spec["features"] if f["name"] != "Feature B"]
        spec_file.write_text(yaml.dump(spec, default_flow_style=False))

        changes = detect_spec_changes(project.id)
        assert len(changes["removed"]) == 1
        assert changes["removed"][0]["name"] == "Feature B"

    def test_detect_modified_feature_resets_status(self, db_path, spec_file, project_with_spec):
        from bob.db import compute_spec_hash, detect_spec_changes, list_features, update_project

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        # Modify Feature A's description
        spec = yaml.safe_load(spec_file.read_text())
        for f in spec["features"]:
            if f["name"] == "Feature A":
                f["description"] = "Updated first feature"
        spec_file.write_text(yaml.dump(spec, default_flow_style=False))

        changes = detect_spec_changes(project.id)
        assert len(changes["modified"]) == 1
        assert changes["modified"][0]["name"] == "Feature A"

        # Verify modified feature was reset to pending
        features = list_features(project_id=project.id)
        for f in features:
            if f.name == "Feature A":
                assert f.status == "pending"

    def test_updates_stored_hash(self, db_path, spec_file, project_with_spec):
        from bob.db import compute_spec_hash, detect_spec_changes, get_project, update_project

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        # Modify spec
        spec = yaml.safe_load(spec_file.read_text())
        spec["features"].append({"name": "New", "description": "new"})
        spec_file.write_text(yaml.dump(spec, default_flow_style=False))

        detect_spec_changes(project.id)
        new_hash = compute_spec_hash(spec_file)

        fetched = get_project(project.id)
        assert fetched.spec_hash == new_hash

    def test_no_changes_returns_empty(self, db_path, spec_file, project_with_spec):
        from bob.db import compute_spec_hash, detect_spec_changes, update_project

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        changes = detect_spec_changes(project.id)
        assert changes["added"] == []
        assert changes["modified"] == []
        assert changes["removed"] == []

    def test_returns_none_when_no_spec_path(self, db_path):
        from bob.db import create_project, detect_spec_changes

        project = create_project(
            name="NoSpec",
            workspace_path="/tmp/nospec",
        )
        result = detect_spec_changes(project.id)
        assert result is None


# ============================================================
# Step 8: Log all spec changes for audit trail
# ============================================================


class TestSpecChangeLogging:
    """Step 8: Spec changes are logged to execution_logs."""

    def test_spec_change_creates_log_entry(self, db_path, spec_file, project_with_spec):
        from bob.db import (
            compute_spec_hash,
            detect_spec_changes,
            query_execution_logs,
            update_project,
        )

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        # Modify spec
        spec = yaml.safe_load(spec_file.read_text())
        spec["features"].append({"name": "LogTest", "description": "log test"})
        spec_file.write_text(yaml.dump(spec, default_flow_style=False))

        detect_spec_changes(project.id)

        logs = query_execution_logs(project_id=project.id)
        spec_change_logs = [lg for lg in logs if "spec_change" in lg.event]
        assert len(spec_change_logs) >= 1

    def test_no_log_when_no_change(self, db_path, spec_file, project_with_spec):
        from bob.db import (
            compute_spec_hash,
            detect_spec_changes,
            query_execution_logs,
            update_project,
        )

        project = project_with_spec
        old_hash = compute_spec_hash(spec_file)
        update_project(project.id, spec_hash=old_hash)

        detect_spec_changes(project.id)

        logs = query_execution_logs(project_id=project.id)
        spec_change_logs = [lg for lg in logs if "spec_change" in lg.event]
        assert len(spec_change_logs) == 0


# ============================================================
# Step 9: Integration test
# ============================================================


class TestSpecChangeIntegration:
    """Step 9: End-to-end spec change detection flow."""

    def test_full_flow_modify_spec_and_detect(self, db_path, tmp_path):
        from bob.db import (
            check_spec_changed,
            compute_spec_hash,
            create_feature,
            create_project,
            detect_spec_changes,
            get_project,
            list_features,
            update_project,
        )

        # 1. Create initial spec
        spec = {
            "name": "IntegrationTest",
            "features": [
                {"name": "Alpha", "description": "alpha desc", "priority": 10},
                {"name": "Beta", "description": "beta desc", "priority": 20},
            ],
        }
        spec_path = tmp_path / "integration_spec.yaml"
        spec_path.write_text(yaml.dump(spec, default_flow_style=False))

        # 2. Create project and features
        project = create_project(
            name="IntegrationTest",
            workspace_path="/tmp/integration",
            spec_path=str(spec_path),
        )
        create_feature(project_id=project.id, name="Alpha", description="alpha desc", priority=10)
        create_feature(project_id=project.id, name="Beta", description="beta desc", priority=20)

        # 3. Store initial hash (like bob plan would)
        initial_hash = compute_spec_hash(spec_path)
        update_project(project.id, spec_hash=initial_hash)

        # 4. Verify no changes detected
        changed, _, _ = check_spec_changed(project.id)
        assert changed is False

        # 5. Modify spec: add a feature, remove one, modify one
        spec["features"] = [
            {"name": "Alpha", "description": "updated alpha", "priority": 10},
            {"name": "Gamma", "description": "gamma desc", "priority": 30},
        ]
        spec_path.write_text(yaml.dump(spec, default_flow_style=False))

        # 6. Detect changes
        changed, old_hash, new_hash = check_spec_changed(project.id)
        assert changed is True

        # 7. Apply changes
        changes = detect_spec_changes(project.id)
        assert len(changes["added"]) == 1   # Gamma
        assert len(changes["modified"]) == 1  # Alpha (description changed)
        assert len(changes["removed"]) == 1  # Beta

        # 8. Verify database updated
        features = list_features(project_id=project.id)
        names = {f.name for f in features}
        assert "Gamma" in names
        assert "Alpha" in names

        # 9. Verify hash updated
        fetched = get_project(project.id)
        assert fetched.spec_hash == new_hash
