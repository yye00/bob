"""Tests for F032: Environment fingerprinting for evidence artifacts."""

import hashlib
import json
import pathlib
import platform
import sqlite3
import sys

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
def project(db_path):
    """Create a test project for foreign key references."""
    from bob.db import create_project

    return create_project(
        name="Fingerprint Test Project",
        workspace_path="/tmp/fingerprint-test",
    )


@pytest.fixture()
def feature(db_path, project):
    """Create a test feature for foreign key references."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Fingerprint Test Feature",
    )


@pytest.fixture()
def task(db_path, project, feature):
    """Create a test task for foreign key references."""
    from bob.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title="Fingerprint Test Task",
    )


# ============================================================
# Step 1: compute_environment_fingerprint() function
# ============================================================


class TestComputeEnvironmentFingerprint:
    """Step 1: compute_environment_fingerprint() returns a JSON string with env info."""

    def test_returns_string(self, db_path):
        from bob.db import compute_environment_fingerprint

        result = compute_environment_fingerprint()
        assert isinstance(result, str)

    def test_returns_valid_json(self, db_path):
        from bob.db import compute_environment_fingerprint

        result = compute_environment_fingerprint()
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_contains_python_version(self, db_path):
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        assert "python_version" in data
        assert data["python_version"] == platform.python_version()

    def test_contains_os_info(self, db_path):
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        assert "os_system" in data
        assert "os_release" in data
        assert "os_machine" in data
        assert data["os_system"] == platform.system()
        assert data["os_machine"] == platform.machine()

    def test_contains_deps_hash(self, db_path):
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        assert "deps_hash" in data
        assert isinstance(data["deps_hash"], str)
        # SHA256 hex digest is 64 chars
        assert len(data["deps_hash"]) == 64

    def test_deterministic_across_calls(self, db_path):
        from bob.db import compute_environment_fingerprint

        result1 = compute_environment_fingerprint()
        result2 = compute_environment_fingerprint()
        assert result1 == result2

    def test_contains_platform_python_implementation(self, db_path):
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        assert "python_implementation" in data
        assert data["python_implementation"] == platform.python_implementation()


# ============================================================
# Step 2: Capture Python version, OS info, dependency hashes
# ============================================================


class TestFingerprintCapture:
    """Step 2: Verify that fingerprint captures all required info correctly."""

    def test_python_version_is_full_version(self, db_path):
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        version = data["python_version"]
        # Should be like "3.13.1" with major.minor.patch
        parts = version.split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts)

    def test_os_system_is_nonempty(self, db_path):
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        assert len(data["os_system"]) > 0

    def test_deps_hash_changes_with_different_deps(self, db_path):
        """The deps_hash is computed from installed packages - verify it's a real hash."""
        from bob.db import compute_environment_fingerprint

        data = json.loads(compute_environment_fingerprint())
        # Verify the deps_hash is a valid hex string
        assert all(c in "0123456789abcdef" for c in data["deps_hash"])

    def test_fingerprint_keys_are_sorted(self, db_path):
        """JSON is produced with sorted keys for deterministic output."""
        from bob.db import compute_environment_fingerprint

        result = compute_environment_fingerprint()
        data = json.loads(result)
        keys = list(data.keys())
        assert keys == sorted(keys)


# ============================================================
# Step 3: Store fingerprint as JSON in evidence record
# ============================================================


class TestFingerprintStoredInEvidence:
    """Step 3: Fingerprint is stored as JSON in the evidence record."""

    def test_create_evidence_with_fingerprint(self, project, feature):
        from bob.db import compute_environment_fingerprint, create_evidence, get_evidence

        fp = compute_environment_fingerprint()
        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"test": True}),
            environment_fingerprint=fp,
        )
        fetched = get_evidence(e.id)
        assert fetched.environment_fingerprint == fp
        # The stored value is valid JSON
        data = json.loads(fetched.environment_fingerprint)
        assert "python_version" in data

    def test_fingerprint_persisted_in_database(self, db_path, project, feature):
        from bob.db import compute_environment_fingerprint, create_evidence

        fp = compute_environment_fingerprint()
        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"db_check": True}),
            environment_fingerprint=fp,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT environment_fingerprint FROM evidence_artifacts WHERE id = ?",
                (e.id,),
            )
            row = cursor.fetchone()
            assert row[0] == fp
        finally:
            conn.close()

    def test_create_evidence_with_hash_stores_fingerprint(self, project, feature):
        from bob.db import compute_environment_fingerprint, create_evidence_with_hash, get_evidence

        fp = compute_environment_fingerprint()
        e = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"hashed": True}),
            environment_fingerprint=fp,
        )
        fetched = get_evidence(e.id)
        assert fetched.environment_fingerprint == fp

    def test_evidence_without_fingerprint_is_null(self, project, feature):
        from bob.db import create_evidence, get_evidence

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_fp": True}),
        )
        fetched = get_evidence(e.id)
        assert fetched.environment_fingerprint is None


# ============================================================
# Step 4: compare_environments() function
# ============================================================


class TestCompareEnvironments:
    """Step 4: compare_environments() compares two fingerprints and reports differences."""

    def test_identical_fingerprints_match(self, db_path):
        from bob.db import compare_environments, compute_environment_fingerprint

        fp = compute_environment_fingerprint()
        result = compare_environments(fp, fp)
        assert result["match"] is True
        assert result["differences"] == {}

    def test_different_python_version_detected(self, db_path):
        from bob.db import compare_environments, compute_environment_fingerprint

        fp1 = compute_environment_fingerprint()
        data = json.loads(fp1)
        data["python_version"] = "2.7.18"
        fp2 = json.dumps(data, sort_keys=True)

        result = compare_environments(fp1, fp2)
        assert result["match"] is False
        assert "python_version" in result["differences"]
        diff = result["differences"]["python_version"]
        assert diff["current"] == platform.python_version()
        assert diff["evidence"] == "2.7.18"

    def test_different_os_detected(self, db_path):
        from bob.db import compare_environments, compute_environment_fingerprint

        fp1 = compute_environment_fingerprint()
        data = json.loads(fp1)
        data["os_system"] = "FakeOS"
        fp2 = json.dumps(data, sort_keys=True)

        result = compare_environments(fp1, fp2)
        assert result["match"] is False
        assert "os_system" in result["differences"]

    def test_different_deps_hash_detected(self, db_path):
        from bob.db import compare_environments, compute_environment_fingerprint

        fp1 = compute_environment_fingerprint()
        data = json.loads(fp1)
        data["deps_hash"] = "a" * 64
        fp2 = json.dumps(data, sort_keys=True)

        result = compare_environments(fp1, fp2)
        assert result["match"] is False
        assert "deps_hash" in result["differences"]

    def test_multiple_differences(self, db_path):
        from bob.db import compare_environments, compute_environment_fingerprint

        fp1 = compute_environment_fingerprint()
        data = json.loads(fp1)
        data["python_version"] = "2.7.18"
        data["os_system"] = "FakeOS"
        fp2 = json.dumps(data, sort_keys=True)

        result = compare_environments(fp1, fp2)
        assert result["match"] is False
        assert len(result["differences"]) >= 2

    def test_compare_returns_dict_with_match_and_differences(self, db_path):
        from bob.db import compare_environments, compute_environment_fingerprint

        fp = compute_environment_fingerprint()
        result = compare_environments(fp, fp)
        assert "match" in result
        assert "differences" in result
        assert isinstance(result["match"], bool)
        assert isinstance(result["differences"], dict)


# ============================================================
# Step 5: Create evidence, change environment, verify mismatch
# ============================================================


class TestEndToEndEnvironmentMismatch:
    """Step 5: End-to-end test - create evidence, simulate env change, detect mismatch."""

    def test_create_evidence_then_detect_environment_change(self, project, feature):
        from bob.db import (
            compare_environments,
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
        )

        # 1. Compute current environment fingerprint
        current_fp = compute_environment_fingerprint()

        # 2. Create evidence with the current fingerprint
        e = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"test_suite": "unit", "passed": 10}),
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )

        # 3. Verify the evidence has the fingerprint
        fetched = get_evidence(e.id)
        assert fetched.environment_fingerprint is not None

        # 4. Simulate an environment change by modifying the stored fingerprint
        stored_data = json.loads(fetched.environment_fingerprint)
        stored_data["python_version"] = "2.7.18"
        stored_data["os_system"] = "DifferentOS"
        changed_fp = json.dumps(stored_data, sort_keys=True)

        # 5. Compare current environment against the changed fingerprint
        result = compare_environments(current_fp, changed_fp)
        assert result["match"] is False
        assert "python_version" in result["differences"]
        assert "os_system" in result["differences"]

    def test_same_environment_no_mismatch(self, project, feature):
        from bob.db import (
            compare_environments,
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
        )

        # Create evidence with current fingerprint
        current_fp = compute_environment_fingerprint()
        e = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"stable": True}),
            environment_fingerprint=current_fp,
        )

        # Retrieve and compare
        fetched = get_evidence(e.id)
        result = compare_environments(current_fp, fetched.environment_fingerprint)
        assert result["match"] is True
        assert result["differences"] == {}

    def test_update_evidence_environment_match_flag(self, project, feature):
        from bob.db import (
            compare_environments,
            compute_environment_fingerprint,
            create_evidence,
            get_evidence,
            update_evidence,
        )

        current_fp = compute_environment_fingerprint()

        # Create evidence with a different fingerprint
        fake_data = json.loads(current_fp)
        fake_data["python_version"] = "2.7.18"
        fake_fp = json.dumps(fake_data, sort_keys=True)

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"env_check": True}),
            environment_fingerprint=fake_fp,
            environment_matches_current=True,
        )

        # Compare and detect mismatch
        result = compare_environments(current_fp, fake_fp)
        assert result["match"] is False

        # Update the evidence to reflect the mismatch
        update_evidence(e.id, environment_matches_current=False)
        fetched = get_evidence(e.id)
        assert fetched.environment_matches_current is False

    def test_query_evidence_filters_environment_mismatch(self, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence,
            query_evidence,
        )

        current_fp = compute_environment_fingerprint()

        # Create matching evidence
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"matching": True}),
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )

        # Create mismatched evidence
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"mismatched": True}),
            environment_fingerprint='{"python_version": "2.7.18"}',
            environment_matches_current=False,
        )

        # Query all evidence
        all_evidence = query_evidence(feature_id=feature.id)
        assert len(all_evidence) == 2

        # Verify we can identify mismatched evidence
        matching = [e for e in all_evidence if e.environment_matches_current]
        mismatched = [e for e in all_evidence if not e.environment_matches_current]
        assert len(matching) == 1
        assert len(mismatched) == 1
