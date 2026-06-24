"""Tests for F100: Comprehensive evidence artifact tracking lifecycle.

Exercises the full evidence lifecycle per acceptance criteria:
  Step 1: Create evidence with hash
  Step 2: Store environment fingerprint
  Step 3: Verify evidence is current (is_current=TRUE)
  Step 4: Advance iteration
  Step 5: Verify old evidence marked stale (is_current=FALSE)
  Step 6: Change environment
  Step 7: Verify environment_matches_current=FALSE
"""

import json
import pathlib
import sqlite3

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
        name="Comprehensive Evidence Test",
        workspace_path="/tmp/comprehensive-evidence-test",
    )


@pytest.fixture()
def feature(db_path, project):
    """Create a test feature for foreign key references."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Comprehensive Evidence Feature",
    )


@pytest.fixture()
def task(db_path, project, feature):
    """Create a test task for foreign key references."""
    from bob.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="validation",
        title="Comprehensive Evidence Task",
    )


# ============================================================
# Step 1: Create evidence with hash
# ============================================================


class TestStep1CreateEvidenceWithHash:
    """Step 1: create_evidence_with_hash() creates evidence with auto-computed SHA256."""

    def test_create_evidence_with_hash_returns_artifact(self, project, feature, task):
        from bob.db import create_evidence_with_hash
        from bob.models import EvidenceArtifact

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"tests_passed": 42, "coverage": 95.3}),
            iteration_created=1,
        )
        assert isinstance(evidence, EvidenceArtifact)

    def test_hash_is_sha256_of_content(self, project, feature):
        import hashlib

        from bob.db import create_evidence_with_hash

        content = json.dumps({"result": "all tests pass", "count": 10})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
            iteration_created=1,
        )
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert evidence.output_hash == expected_hash

    def test_hash_persisted_in_database(self, db_path, project, feature):
        import hashlib

        from bob.db import create_evidence_with_hash

        content = json.dumps({"persisted_hash": True})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
            iteration_created=1,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT output_hash FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row[0] == hashlib.sha256(content.encode("utf-8")).hexdigest()
        finally:
            conn.close()

    def test_verify_evidence_after_creation(self, project, feature):
        from bob.db import create_evidence_with_hash, verify_evidence

        content = json.dumps({"verify_test": True})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
            iteration_created=1,
        )

        result = verify_evidence(evidence.id)
        assert result is not None
        assert result.verified is True
        assert result.expected_hash == result.actual_hash


# ============================================================
# Step 2: Store environment fingerprint
# ============================================================


class TestStep2StoreEnvironmentFingerprint:
    """Step 2: Evidence stores environment fingerprint as JSON."""

    def test_evidence_stores_fingerprint(self, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
        )

        fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"fp_test": True}),
            iteration_created=1,
            environment_fingerprint=fp,
        )

        fetched = get_evidence(evidence.id)
        assert fetched.environment_fingerprint == fp

    def test_fingerprint_is_valid_json(self, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
        )

        fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"json_check": True}),
            iteration_created=1,
            environment_fingerprint=fp,
        )

        fetched = get_evidence(evidence.id)
        data = json.loads(fetched.environment_fingerprint)
        assert "python_version" in data
        assert "os_system" in data
        assert "deps_hash" in data

    def test_fingerprint_persisted_in_database(self, db_path, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
        )

        fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"db_fp": True}),
            iteration_created=1,
            environment_fingerprint=fp,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT environment_fingerprint FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row[0] == fp
        finally:
            conn.close()


# ============================================================
# Step 3: Verify evidence is current (is_current=TRUE)
# ============================================================


class TestStep3VerifyEvidenceIsCurrent:
    """Step 3: Newly created evidence has is_current=TRUE."""

    def test_new_evidence_is_current(self, project, feature):
        from bob.db import create_evidence_with_hash, get_evidence

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"current_check": True}),
            iteration_created=1,
        )

        fetched = get_evidence(evidence.id)
        assert fetched.is_current is True

    def test_query_evidence_finds_current(self, project, feature):
        from bob.db import create_evidence_with_hash, query_evidence

        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"query_current": True}),
            iteration_created=1,
        )

        results = query_evidence(feature_id=feature.id, is_current=True)
        assert len(results) == 1
        assert results[0].is_current is True

    def test_is_current_true_in_database(self, db_path, project, feature):
        from bob.db import create_evidence_with_hash

        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"db_current": True}),
            iteration_created=1,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT is_current FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row[0] == 1  # SQLite TRUE
        finally:
            conn.close()


# ============================================================
# Step 4: Advance iteration
# ============================================================


class TestStep4AdvanceIteration:
    """Step 4: Create new evidence at a later iteration and mark old stale."""

    def test_create_evidence_at_higher_iteration(self, project, feature):
        from bob.db import create_evidence_with_hash, get_current_iteration

        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"iter_1": True}),
            iteration_created=1,
        )
        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"iter_5": True}),
            iteration_created=5,
        )

        current_iter = get_current_iteration(feature_id=feature.id)
        assert current_iter == 5

    def test_mark_evidence_stale_after_advance(self, project, feature):
        from bob.db import create_evidence_with_hash, mark_evidence_stale

        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old_iter": True}),
            iteration_created=1,
        )

        count = mark_evidence_stale(
            feature_id=feature.id,
            current_iteration=5,
            staleness_threshold=2,
        )
        assert count == 1


# ============================================================
# Step 5: Verify old evidence marked stale (is_current=FALSE)
# ============================================================


class TestStep5VerifyOldEvidenceStale:
    """Step 5: After advancing iteration, old evidence has is_current=FALSE."""

    def test_old_evidence_is_not_current(self, project, feature):
        from bob.db import (
            create_evidence_with_hash,
            get_evidence,
            mark_evidence_stale,
        )

        e_old = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"stale_test": True}),
            iteration_created=1,
        )

        mark_evidence_stale(
            feature_id=feature.id,
            current_iteration=5,
            staleness_threshold=2,
        )

        fetched = get_evidence(e_old.id)
        assert fetched.is_current is False

    def test_new_evidence_remains_current(self, project, feature):
        from bob.db import (
            create_evidence_with_hash,
            get_evidence,
            mark_evidence_stale,
        )

        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old": True}),
            iteration_created=1,
        )
        e_new = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"new": True}),
            iteration_created=5,
        )

        mark_evidence_stale(
            feature_id=feature.id,
            current_iteration=5,
            staleness_threshold=2,
        )

        fetched = get_evidence(e_new.id)
        assert fetched.is_current is True

    def test_query_filters_stale_evidence(self, project, feature):
        from bob.db import (
            create_evidence_with_hash,
            mark_evidence_stale,
            query_evidence,
        )

        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old": True}),
            iteration_created=1,
        )
        create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"new": True}),
            iteration_created=5,
        )

        mark_evidence_stale(
            feature_id=feature.id,
            current_iteration=5,
            staleness_threshold=2,
        )

        current = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current) == 1
        assert json.loads(current[0].content) == {"new": True}


# ============================================================
# Step 6: Change environment
# ============================================================


class TestStep6ChangeEnvironment:
    """Step 6: Simulate environment change and detect mismatch."""

    def test_detect_environment_change(self, project, feature):
        from bob.db import (
            compare_environments,
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
        )

        current_fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"env_change_test": True}),
            iteration_created=1,
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )

        # Simulate environment change
        fetched = get_evidence(evidence.id)
        stored_data = json.loads(fetched.environment_fingerprint)
        stored_data["python_version"] = "2.7.18"
        changed_fp = json.dumps(stored_data, sort_keys=True)

        result = compare_environments(current_fp, changed_fp)
        assert result["match"] is False
        assert "python_version" in result["differences"]

    def test_compare_environments_reports_multiple_diffs(self, project, feature):
        from bob.db import (
            compare_environments,
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
        )

        current_fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"multi_diff": True}),
            iteration_created=1,
            environment_fingerprint=current_fp,
        )

        fetched = get_evidence(evidence.id)
        stored_data = json.loads(fetched.environment_fingerprint)
        stored_data["python_version"] = "2.7.18"
        stored_data["os_system"] = "FakeOS"
        stored_data["deps_hash"] = "a" * 64
        changed_fp = json.dumps(stored_data, sort_keys=True)

        result = compare_environments(current_fp, changed_fp)
        assert result["match"] is False
        assert len(result["differences"]) >= 3


# ============================================================
# Step 7: Verify environment_matches_current=FALSE
# ============================================================


class TestStep7VerifyEnvironmentMatchesFalse:
    """Step 7: After env change, update evidence environment_matches_current=FALSE."""

    def test_update_environment_matches_to_false(self, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_evidence,
            update_evidence,
        )

        current_fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"env_match_false": True}),
            iteration_created=1,
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )

        # Simulate detecting a mismatch and updating the flag
        update_evidence(evidence.id, environment_matches_current=False)

        fetched = get_evidence(evidence.id)
        assert fetched.environment_matches_current is False

    def test_environment_matches_false_in_database(self, db_path, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
            update_evidence,
        )

        current_fp = compute_environment_fingerprint()
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"db_env_match": True}),
            iteration_created=1,
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )

        update_evidence(evidence.id, environment_matches_current=False)

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT environment_matches_current FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row[0] == 0  # SQLite FALSE
        finally:
            conn.close()

    def test_query_finds_environment_mismatched_evidence(self, project, feature):
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
            query_evidence,
            update_evidence,
        )

        current_fp = compute_environment_fingerprint()

        # Create matching evidence
        e_match = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"matching": True}),
            iteration_created=5,
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )

        # Create evidence that will be marked as mismatched
        e_mismatch = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"mismatched": True}),
            iteration_created=5,
            environment_fingerprint=current_fp,
            environment_matches_current=True,
        )
        update_evidence(e_mismatch.id, environment_matches_current=False)

        all_evidence = query_evidence(feature_id=feature.id)
        matching = [e for e in all_evidence if e.environment_matches_current]
        mismatched = [e for e in all_evidence if not e.environment_matches_current]
        assert len(matching) == 1
        assert len(mismatched) == 1
        assert mismatched[0].id == e_mismatch.id


# ============================================================
# Full End-to-End Lifecycle Test
# ============================================================


class TestFullLifecycle:
    """Complete lifecycle test exercising all 7 acceptance criteria in sequence."""

    def test_complete_evidence_lifecycle(self, db_path, project, feature, task):
        """Walk through the entire evidence lifecycle:
        1. Create evidence with hash
        2. Store environment fingerprint
        3. Verify is_current=TRUE
        4. Advance iteration
        5. Verify old evidence is_current=FALSE
        6. Change environment
        7. Verify environment_matches_current=FALSE
        """
        from bob.db import (
            compare_environments,
            compute_environment_fingerprint,
            create_evidence_with_hash,
            get_current_iteration,
            get_evidence,
            mark_evidence_stale,
            query_evidence,
            update_evidence,
            verify_evidence,
        )

        # --- Step 1: Create evidence with hash ---
        content_v1 = json.dumps({"test_suite": "unit", "passed": 42, "failed": 0})
        fp = compute_environment_fingerprint()

        e1 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=content_v1,
            iteration_created=1,
            environment_fingerprint=fp,
            environment_matches_current=True,
        )
        assert e1.output_hash is not None
        assert len(e1.output_hash) == 64  # SHA256 hex digest

        # Verify hash correctness
        vr = verify_evidence(e1.id)
        assert vr.verified is True

        # --- Step 2: Store environment fingerprint ---
        fetched = get_evidence(e1.id)
        assert fetched.environment_fingerprint == fp
        fp_data = json.loads(fetched.environment_fingerprint)
        assert "python_version" in fp_data
        assert "os_system" in fp_data
        assert "deps_hash" in fp_data

        # --- Step 3: Verify evidence is current (is_current=TRUE) ---
        assert fetched.is_current is True
        current_results = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current_results) == 1
        assert current_results[0].id == e1.id

        # --- Step 4: Advance iteration ---
        content_v2 = json.dumps({"test_suite": "unit", "passed": 50, "failed": 0})
        e2 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=content_v2,
            iteration_created=5,
            environment_fingerprint=fp,
            environment_matches_current=True,
        )

        current_iter = get_current_iteration(feature_id=feature.id)
        assert current_iter == 5

        # Mark stale evidence (threshold=2: iteration 1 at current 5 => gap 4 > 2)
        stale_count = mark_evidence_stale(
            feature_id=feature.id,
            current_iteration=current_iter,
            staleness_threshold=2,
        )
        assert stale_count == 1

        # --- Step 5: Verify old evidence marked stale (is_current=FALSE) ---
        e1_after = get_evidence(e1.id)
        assert e1_after.is_current is False

        e2_after = get_evidence(e2.id)
        assert e2_after.is_current is True

        current_only = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current_only) == 1
        assert current_only[0].id == e2.id

        # --- Step 6: Change environment ---
        # Simulate environment change by creating a modified fingerprint
        original_fp_data = json.loads(fp)
        original_fp_data["python_version"] = "2.7.18"
        original_fp_data["os_system"] = "DifferentOS"
        changed_fp = json.dumps(original_fp_data, sort_keys=True)

        comparison = compare_environments(fp, changed_fp)
        assert comparison["match"] is False
        assert "python_version" in comparison["differences"]
        assert "os_system" in comparison["differences"]

        # --- Step 7: Verify environment_matches_current=FALSE ---
        # Update evidence to reflect the environment mismatch
        update_evidence(e2.id, environment_matches_current=False)

        e2_final = get_evidence(e2.id)
        assert e2_final.environment_matches_current is False

        # Verify in raw database
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT environment_matches_current FROM evidence_artifacts WHERE id = ?",
                (e2.id,),
            )
            row = cursor.fetchone()
            assert row[0] == 0  # SQLite FALSE
        finally:
            conn.close()

    def test_lifecycle_with_multiple_features(self, db_path, project):
        """Verify the lifecycle works correctly with multiple features (isolation)."""
        from bob.db import (
            compute_environment_fingerprint,
            create_evidence_with_hash,
            create_feature,
            get_evidence,
            mark_evidence_stale,
            query_evidence,
        )

        f1 = create_feature(project_id=project.id, name="Feature A")
        f2 = create_feature(project_id=project.id, name="Feature B")

        fp = compute_environment_fingerprint()

        # Create evidence for both features at iteration 1
        e1_f1 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=f1.id,
            type="test_output",
            content=json.dumps({"feature": "A", "iter": 1}),
            iteration_created=1,
            environment_fingerprint=fp,
        )
        e1_f2 = create_evidence_with_hash(
            project_id=project.id,
            feature_id=f2.id,
            type="test_output",
            content=json.dumps({"feature": "B", "iter": 1}),
            iteration_created=1,
            environment_fingerprint=fp,
        )

        # Advance only feature A to iteration 5
        create_evidence_with_hash(
            project_id=project.id,
            feature_id=f1.id,
            type="test_output",
            content=json.dumps({"feature": "A", "iter": 5}),
            iteration_created=5,
            environment_fingerprint=fp,
        )

        # Mark stale for feature A only
        mark_evidence_stale(feature_id=f1.id, current_iteration=5, staleness_threshold=2)

        # Feature A iter 1 evidence should be stale
        assert get_evidence(e1_f1.id).is_current is False

        # Feature B iter 1 evidence should still be current (unaffected)
        assert get_evidence(e1_f2.id).is_current is True

        # Feature A should have 1 current evidence, Feature B should have 1
        assert len(query_evidence(feature_id=f1.id, is_current=True)) == 1
        assert len(query_evidence(feature_id=f2.id, is_current=True)) == 1

    def test_lifecycle_reproducibility_check(self, project, feature):
        """Verify evidence reproducibility using check_reproducibility."""
        from bob.db import (
            check_reproducibility,
            create_evidence_with_hash,
        )

        content = json.dumps({"reproducible_test": True, "value": 42})
        evidence = create_evidence_with_hash(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=content,
            iteration_created=1,
        )

        # Same content should be reproducible
        assert check_reproducibility(evidence.id, content) is True

        # Different content should not be reproducible
        different = json.dumps({"reproducible_test": True, "value": 99})
        assert check_reproducibility(evidence.id, different) is False
