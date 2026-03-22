"""Tests for F030: Evidence artifact verification (hash checking, reproducibility)."""

import hashlib
import json
import pathlib
import sqlite3

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


@pytest.fixture()
def project(db_path):
    """Create a test project for foreign key references."""
    from bob3.db import create_project

    return create_project(
        name="Verification Test Project",
        workspace_path="/tmp/verification-test",
    )


@pytest.fixture()
def feature(db_path, project):
    """Create a test feature for foreign key references."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Verification Test Feature",
    )


@pytest.fixture()
def task(db_path, project, feature):
    """Create a test task for foreign key references."""
    from bob3.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title="Verification Test Task",
    )


# ============================================================
# Step 1: create_evidence_with_hash() computes SHA256
# ============================================================


class TestCreateEvidenceWithHash:
    """Step 1: create_evidence_with_hash() computes SHA256 of content and stores it."""

    def test_returns_evidence_artifact(self, project, feature, task):
        from bob3.db import create_evidence_with_hash
        from bob3.models import EvidenceArtifact

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"stdout": "All tests passed"}),
        )
        assert isinstance(evidence, EvidenceArtifact)

    def test_computes_sha256_hash(self, project, feature):
        from bob3.db import create_evidence_with_hash

        content = json.dumps({"result": "ok"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert evidence.output_hash == expected_hash

    def test_hash_is_stored_in_database(self, db_path, project, feature):
        from bob3.db import create_evidence_with_hash

        content = json.dumps({"persisted": True})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT output_hash FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert row[0] == expected_hash
        finally:
            conn.close()

    def test_preserves_all_other_fields(self, project, feature, task):
        from bob3.db import create_evidence_with_hash

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="build_output",
            content=json.dumps({"log": "build succeeded"}),
            attempt_number=2,
            is_current=True,
            iteration_created=3,
            environment_fingerprint=json.dumps({"python": "3.13"}),
            environment_matches_current=True,
        )
        assert evidence.project_id == project.id
        assert evidence.feature_id == feature.id
        assert evidence.task_id == task.id
        assert evidence.type == "build_output"
        assert evidence.attempt_number == 2
        assert evidence.is_current is True
        assert evidence.iteration_created == 3

    def test_different_content_produces_different_hashes(self, project, feature):
        from bob3.db import create_evidence_with_hash

        e1 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"data": "first"}),
        )
        e2 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"data": "second"}),
        )
        assert e1.output_hash != e2.output_hash

    def test_same_content_produces_same_hash(self, project, feature):
        from bob3.db import create_evidence_with_hash

        content = json.dumps({"data": "identical"})
        e1 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        e2 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        assert e1.output_hash == e2.output_hash

    def test_accepts_custom_evidence_id(self, project, feature):
        from bob3.db import create_evidence_with_hash

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"custom": True}),
            evidence_id="custom-hash-evidence-001",
        )
        assert evidence.id == "custom-hash-evidence-001"
        assert evidence.output_hash is not None


# ============================================================
# Step 2: verify_evidence() recomputes hash
# ============================================================


class TestVerifyEvidence:
    """Step 2: verify_evidence() recomputes hash and checks for tampering."""

    def test_verify_unmodified_evidence_passes(self, project, feature):
        from bob3.db import create_evidence_with_hash, verify_evidence

        content = json.dumps({"status": "pass"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        result = verify_evidence(evidence.id)
        assert result.verified is True
        assert result.evidence_id == evidence.id

    def test_verify_modified_evidence_fails(self, db_path, project, feature):
        from bob3.db import create_evidence_with_hash, verify_evidence

        content = json.dumps({"status": "pass"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )

        # Directly modify the content in the database (simulate tampering)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE evidence_artifacts SET content = ? WHERE id = ?",
                (json.dumps({"status": "TAMPERED"}), evidence.id),
            )
            conn.commit()
        finally:
            conn.close()

        result = verify_evidence(evidence.id)
        assert result.verified is False

    def test_verify_evidence_updates_verification_fields(self, project, feature):
        from bob3.db import create_evidence_with_hash, get_evidence, verify_evidence

        content = json.dumps({"status": "verified"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        verify_evidence(evidence.id)

        fetched = get_evidence(evidence.id)
        assert fetched.verification_passed is True
        assert fetched.verification_run_at is not None

    def test_verify_tampered_evidence_sets_verification_failed(self, db_path, project, feature):
        from bob3.db import create_evidence_with_hash, get_evidence, verify_evidence

        content = json.dumps({"original": True})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )

        # Tamper
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE evidence_artifacts SET content = ? WHERE id = ?",
                (json.dumps({"original": False}), evidence.id),
            )
            conn.commit()
        finally:
            conn.close()

        verify_evidence(evidence.id)
        fetched = get_evidence(evidence.id)
        assert fetched.verification_passed is False

    def test_verify_nonexistent_evidence_returns_none(self, db_path):
        from bob3.db import verify_evidence

        result = verify_evidence("nonexistent-id")
        assert result is None

    def test_verify_evidence_without_hash_returns_no_hash(self, project, feature):
        from bob3.db import create_evidence, verify_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_hash": True}),
        )
        result = verify_evidence(evidence.id)
        assert result.verified is False
        assert result.reason == "no_hash"

    def test_verify_returns_expected_and_actual_hash(self, db_path, project, feature):
        from bob3.db import create_evidence_with_hash, verify_evidence

        content = json.dumps({"data": "hash-test"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )

        # Tamper
        tampered_content = json.dumps({"data": "tampered"})
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE evidence_artifacts SET content = ? WHERE id = ?",
                (tampered_content, evidence.id),
            )
            conn.commit()
        finally:
            conn.close()

        result = verify_evidence(evidence.id)
        assert result.expected_hash == hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result.actual_hash == hashlib.sha256(tampered_content.encode("utf-8")).hexdigest()
        assert result.expected_hash != result.actual_hash


# ============================================================
# Step 3: Reproducibility checking
# ============================================================


class TestReproducibilityChecking:
    """Step 3: check_reproducibility() re-runs and compares hashes."""

    def test_mark_evidence_reproducible(self, project, feature):
        from bob3.db import create_evidence_with_hash, check_reproducibility, get_evidence

        content = json.dumps({"test": "reproducible"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )

        # Check reproducibility with same content
        result = check_reproducibility(evidence.id, content)
        assert result is True

        fetched = get_evidence(evidence.id)
        assert fetched.reproducible is True

    def test_mark_evidence_not_reproducible(self, project, feature):
        from bob3.db import create_evidence_with_hash, check_reproducibility, get_evidence

        original_content = json.dumps({"test": "original"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=original_content,
        )

        # Check with different content (not reproducible)
        different_content = json.dumps({"test": "different_run"})
        result = check_reproducibility(evidence.id, different_content)
        assert result is False

        fetched = get_evidence(evidence.id)
        assert fetched.reproducible is False

    def test_check_reproducibility_nonexistent_returns_none(self, db_path):
        from bob3.db import check_reproducibility

        result = check_reproducibility("nonexistent-id", "content")
        assert result is None

    def test_check_reproducibility_without_hash_returns_none(self, project, feature):
        from bob3.db import create_evidence, check_reproducibility

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_hash": True}),
        )
        result = check_reproducibility(evidence.id, json.dumps({"no_hash": True}))
        assert result is None


# ============================================================
# Step 4: End-to-end: create, verify, modify, detect change
# ============================================================


class TestEndToEndVerification:
    """Step 4: Full lifecycle - create, verify, tamper, detect."""

    def test_full_lifecycle(self, db_path, project, feature, task):
        from bob3.db import create_evidence_with_hash, verify_evidence, get_evidence

        content = json.dumps({"test_suite": "unit", "passed": 42, "failed": 0})

        # 1. Create evidence with hash
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=content,
        )
        assert evidence.output_hash is not None

        # 2. Verify it (should pass)
        result = verify_evidence(evidence.id)
        assert result.verified is True

        # 3. Modify the content in the database (simulate tampering)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE evidence_artifacts SET content = ? WHERE id = ?",
                (json.dumps({"test_suite": "unit", "passed": 42, "failed": 1}), evidence.id),
            )
            conn.commit()
        finally:
            conn.close()

        # 4. Verify again - should detect the change
        result = verify_evidence(evidence.id)
        assert result.verified is False

        # 5. Check stored verification state
        fetched = get_evidence(evidence.id)
        assert fetched.verification_passed is False
        assert fetched.verification_run_at is not None


# ============================================================
# Step 5: output_hash is stored correctly
# ============================================================


class TestOutputHashStorage:
    """Step 5: Verify output_hash is stored and retrievable correctly."""

    def test_output_hash_persisted_on_create(self, db_path, project, feature):
        from bob3.db import create_evidence_with_hash

        content = json.dumps({"step5": "test"})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )

        # Verify hash is in DB
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT output_hash FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row[0] == evidence.output_hash
        finally:
            conn.close()

    def test_output_hash_retrievable_via_get(self, project, feature):
        from bob3.db import create_evidence_with_hash, get_evidence

        content = json.dumps({"retrieve": True})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        fetched = get_evidence(evidence.id)
        assert fetched.output_hash == evidence.output_hash
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert fetched.output_hash == expected

    def test_output_hash_is_64_char_hex(self, project, feature):
        from bob3.db import create_evidence_with_hash

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"hex": True}),
        )
        assert len(evidence.output_hash) == 64
        assert all(c in "0123456789abcdef" for c in evidence.output_hash)

    def test_output_hash_queryable_in_evidence_list(self, project, feature):
        from bob3.db import create_evidence_with_hash, query_evidence

        content = json.dumps({"query": "test"})
        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
        )
        results = query_evidence(feature_id=feature.id)
        assert len(results) == 1
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert results[0].output_hash == expected
