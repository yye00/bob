"""Tests for F031: Evidence staleness detection (iteration tracking)."""

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
        name="Staleness Test Project",
        workspace_path="/tmp/staleness-test",
    )


@pytest.fixture()
def feature(db_path, project):
    """Create a test feature for foreign key references."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Staleness Test Feature",
    )


@pytest.fixture()
def task(db_path, project, feature):
    """Create a test task for foreign key references."""
    from bob.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title="Staleness Test Task",
    )


# ============================================================
# Step 1: mark_evidence_stale() function
# ============================================================


class TestMarkEvidenceStale:
    """Step 1: mark_evidence_stale() sets is_current=FALSE for old evidence."""

    def test_mark_evidence_stale_returns_count(self, project, feature):
        """mark_evidence_stale returns the number of evidence items marked stale."""
        from bob.db import create_evidence, mark_evidence_stale

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"v": 1}),
            is_current=True,
            iteration_created=1,
        )

        count = mark_evidence_stale(feature_id=feature.id, current_iteration=4)
        assert isinstance(count, int)
        assert count == 1

    def test_mark_evidence_stale_sets_is_current_false(self, project, feature):
        """Evidence older than threshold iterations is marked not current."""
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old": True}),
            is_current=True,
            iteration_created=1,
        )

        mark_evidence_stale(feature_id=feature.id, current_iteration=4)

        fetched = get_evidence(e.id)
        assert fetched.is_current is False

    def test_mark_evidence_stale_does_not_affect_recent(self, project, feature):
        """Evidence from recent iterations is not marked stale."""
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"recent": True}),
            is_current=True,
            iteration_created=3,
        )

        mark_evidence_stale(feature_id=feature.id, current_iteration=4)

        fetched = get_evidence(e.id)
        assert fetched.is_current is True

    def test_mark_evidence_stale_default_threshold_is_2(self, project, feature):
        """Default staleness threshold is 2 iterations behind current."""
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        # iteration 2, current=4 => gap of 2 => NOT stale (exactly at threshold)
        e_at_threshold = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"at_threshold": True}),
            is_current=True,
            iteration_created=2,
        )

        # iteration 1, current=4 => gap of 3 => stale
        e_beyond = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"beyond": True}),
            is_current=True,
            iteration_created=1,
        )

        count = mark_evidence_stale(feature_id=feature.id, current_iteration=4)
        assert count == 1

        assert get_evidence(e_at_threshold.id).is_current is True
        assert get_evidence(e_beyond.id).is_current is False

    def test_mark_evidence_stale_custom_threshold(self, project, feature):
        """Staleness threshold can be customized."""
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"custom": True}),
            is_current=True,
            iteration_created=3,
        )

        # threshold=1 means evidence must be within 1 iteration of current
        # current=4, created=3 => gap=1 => NOT stale (exactly at threshold)
        count = mark_evidence_stale(
            feature_id=feature.id, current_iteration=4, staleness_threshold=1
        )
        assert count == 0
        assert get_evidence(e.id).is_current is True

        # current=5, created=3 => gap=2 => stale (exceeds threshold of 1)
        count = mark_evidence_stale(
            feature_id=feature.id, current_iteration=5, staleness_threshold=1
        )
        assert count == 1
        assert get_evidence(e.id).is_current is False

    def test_mark_evidence_stale_skips_already_stale(self, project, feature):
        """Evidence already marked not current is not counted again."""
        from bob.db import create_evidence, mark_evidence_stale

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"already_stale": True}),
            is_current=False,
            iteration_created=1,
        )

        count = mark_evidence_stale(feature_id=feature.id, current_iteration=10)
        assert count == 0

    def test_mark_evidence_stale_skips_null_iteration(self, project, feature):
        """Evidence with no iteration_created is not marked stale."""
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_iter": True}),
            is_current=True,
            # iteration_created not set (None)
        )

        count = mark_evidence_stale(feature_id=feature.id, current_iteration=10)
        assert count == 0
        assert get_evidence(e.id).is_current is True

    def test_mark_evidence_stale_no_evidence_returns_zero(self, project, feature):
        """Returns 0 when no evidence exists for the feature."""
        from bob.db import mark_evidence_stale

        count = mark_evidence_stale(feature_id=feature.id, current_iteration=5)
        assert count == 0


# ============================================================
# Step 2: Track iteration_created for each evidence
# ============================================================


class TestIterationCreatedTracking:
    """Step 2: iteration_created field is properly stored and retrieved."""

    def test_iteration_created_stored_on_create(self, project, feature):
        from bob.db import create_evidence, get_evidence

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"iter": 5}),
            iteration_created=5,
        )
        fetched = get_evidence(e.id)
        assert fetched.iteration_created == 5

    def test_iteration_created_default_is_none(self, project, feature):
        from bob.db import create_evidence, get_evidence

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_iter": True}),
        )
        fetched = get_evidence(e.id)
        assert fetched.iteration_created is None

    def test_iteration_created_persisted_in_database(self, db_path, project, feature):
        from bob.db import create_evidence

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"db_check": True}),
            iteration_created=7,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT iteration_created FROM evidence_artifacts WHERE id = ?",
                (e.id,),
            )
            row = cursor.fetchone()
            assert row[0] == 7
        finally:
            conn.close()

    def test_multiple_evidence_different_iterations(self, project, feature):
        from bob.db import create_evidence, query_evidence

        for i in range(1, 4):
            create_evidence(
                project_id=project.id,
                feature_id=feature.id,
                type="test_output",
                content=json.dumps({"iteration": i}),
                iteration_created=i,
            )

        results = query_evidence(feature_id=feature.id)
        iterations = [e.iteration_created for e in results]
        assert iterations == [1, 2, 3]


# ============================================================
# Step 3: get_current_iteration() - compare current vs evidence iteration
# ============================================================


class TestGetCurrentIteration:
    """Step 3: get_current_iteration() returns the max iteration for a feature."""

    def test_get_current_iteration_returns_max(self, project, feature):
        from bob.db import create_evidence, get_current_iteration

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"v": 1}),
            iteration_created=1,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"v": 3}),
            iteration_created=3,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"v": 2}),
            iteration_created=2,
        )

        current = get_current_iteration(feature_id=feature.id)
        assert current == 3

    def test_get_current_iteration_no_evidence_returns_zero(self, project, feature):
        from bob.db import get_current_iteration

        current = get_current_iteration(feature_id=feature.id)
        assert current == 0

    def test_get_current_iteration_null_iterations_returns_zero(self, project, feature):
        from bob.db import create_evidence, get_current_iteration

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_iter": True}),
        )

        current = get_current_iteration(feature_id=feature.id)
        assert current == 0

    def test_get_current_iteration_mixed_null_and_set(self, project, feature):
        from bob.db import create_evidence, get_current_iteration

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"no_iter": True}),
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"iter": 5}),
            iteration_created=5,
        )

        current = get_current_iteration(feature_id=feature.id)
        assert current == 5


# ============================================================
# Step 4: Set is_current=FALSE for old evidence
# ============================================================


class TestStalenessUpdate:
    """Step 4: Verify is_current=FALSE is set correctly in the database."""

    def test_stale_evidence_is_current_false_in_db(self, db_path, project, feature):
        from bob.db import create_evidence, mark_evidence_stale

        e = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"stale_db": True}),
            is_current=True,
            iteration_created=1,
        )

        mark_evidence_stale(feature_id=feature.id, current_iteration=5)

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT is_current FROM evidence_artifacts WHERE id = ?",
                (e.id,),
            )
            row = cursor.fetchone()
            assert row[0] == 0  # SQLite stores FALSE as 0
        finally:
            conn.close()

    def test_multiple_stale_marked_at_once(self, project, feature):
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        e1 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old1": True}),
            is_current=True,
            iteration_created=1,
        )
        e2 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old2": True}),
            is_current=True,
            iteration_created=1,
        )
        e3 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"recent": True}),
            is_current=True,
            iteration_created=5,
        )

        count = mark_evidence_stale(feature_id=feature.id, current_iteration=5)
        assert count == 2

        assert get_evidence(e1.id).is_current is False
        assert get_evidence(e2.id).is_current is False
        assert get_evidence(e3.id).is_current is True

    def test_only_specified_feature_affected(self, project):
        from bob.db import create_evidence, create_feature, get_evidence, mark_evidence_stale

        f1 = create_feature(project_id=project.id, name="Feature A")
        f2 = create_feature(project_id=project.id, name="Feature B")

        e1 = create_evidence(
            project_id=project.id,
            feature_id=f1.id,
            type="test_output",
            content=json.dumps({"f1": True}),
            is_current=True,
            iteration_created=1,
        )
        e2 = create_evidence(
            project_id=project.id,
            feature_id=f2.id,
            type="test_output",
            content=json.dumps({"f2": True}),
            is_current=True,
            iteration_created=1,
        )

        mark_evidence_stale(feature_id=f1.id, current_iteration=5)

        assert get_evidence(e1.id).is_current is False
        assert get_evidence(e2.id).is_current is True  # Other feature unaffected


# ============================================================
# Step 5: End-to-end - create at iteration 1, advance to 3, verify stale
# ============================================================


class TestEndToEndStaleness:
    """Step 5: Full lifecycle test per acceptance criteria."""

    def test_create_at_iter1_advance_to_iter3_verify_stale(self, project, feature):
        """Create evidence at iteration 1, advance to iteration 3, verify marked stale."""
        from bob.db import create_evidence, get_current_iteration, get_evidence, mark_evidence_stale

        # Step 1: Create evidence at iteration 1
        e_old = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"test": "iteration 1 evidence"}),
            is_current=True,
            iteration_created=1,
        )

        # Verify it starts as current
        assert get_evidence(e_old.id).is_current is True

        # Step 2: Add evidence at iteration 2
        e_mid = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"test": "iteration 2 evidence"}),
            is_current=True,
            iteration_created=2,
        )

        # Step 3: Add evidence at iteration 3 (simulates advancing to iter 3)
        e_new = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"test": "iteration 3 evidence"}),
            is_current=True,
            iteration_created=3,
        )

        # Get current iteration (should be 3)
        current_iter = get_current_iteration(feature_id=feature.id)
        assert current_iter == 3

        # Step 4: Mark stale evidence (threshold=2 by default)
        # iteration 1 evidence: gap = 3 - 1 = 2, NOT > 2, so NOT stale with default
        # We need current_iteration=4 or threshold=1 to make iteration 1 stale
        # Let's use the exact scenario: current=3, threshold=1
        count = mark_evidence_stale(
            feature_id=feature.id,
            current_iteration=current_iter,
            staleness_threshold=1,
        )

        # iteration 1: gap = 3 - 1 = 2 > 1 => stale
        # iteration 2: gap = 3 - 2 = 1 => NOT stale (exactly at threshold)
        # iteration 3: gap = 3 - 3 = 0 => NOT stale
        assert count == 1

        # Step 5: Verify the iteration 1 evidence is marked stale
        assert get_evidence(e_old.id).is_current is False
        assert get_evidence(e_mid.id).is_current is True
        assert get_evidence(e_new.id).is_current is True

    def test_create_at_iter1_advance_to_iter3_default_threshold(self, project, feature):
        """With default threshold=2, evidence at iteration 1 becomes stale at iteration 4."""
        from bob.db import create_evidence, get_evidence, mark_evidence_stale

        e_iter1 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"iter": 1}),
            is_current=True,
            iteration_created=1,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"iter": 3}),
            is_current=True,
            iteration_created=3,
        )

        # At current_iteration=3 with default threshold=2:
        # gap = 3 - 1 = 2, NOT > 2 => NOT stale
        count = mark_evidence_stale(feature_id=feature.id, current_iteration=3)
        assert count == 0
        assert get_evidence(e_iter1.id).is_current is True

        # At current_iteration=4 with default threshold=2:
        # gap = 4 - 1 = 3 > 2 => stale
        count = mark_evidence_stale(feature_id=feature.id, current_iteration=4)
        assert count == 1
        assert get_evidence(e_iter1.id).is_current is False

    def test_staleness_with_query_evidence_filter(self, project, feature):
        """After marking stale, query_evidence with is_current=True excludes them."""
        from bob.db import create_evidence, mark_evidence_stale, query_evidence

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"old": True}),
            is_current=True,
            iteration_created=1,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"new": True}),
            is_current=True,
            iteration_created=5,
        )

        # Before staleness check: both are current
        current_before = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current_before) == 2

        # Mark stale
        mark_evidence_stale(feature_id=feature.id, current_iteration=5)

        # After staleness check: only new evidence is current
        current_after = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current_after) == 1
        assert json.loads(current_after[0].content) == {"new": True}

        # All evidence still exists
        all_evidence = query_evidence(feature_id=feature.id)
        assert len(all_evidence) == 2
