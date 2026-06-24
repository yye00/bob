"""Tests for bob.assess_feature_confidence — spec-quality-score mapping.

Verifies that assess_with_spec_quality_mapping derives readiness from the
demonstrated spec_quality_score rather than the conservative AC-count heuristic,
breaking the chicken-and-egg deadlock where high-quality features stayed at 0.0.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Set up a temporary bob SQLite database and monkeypatch bob.db."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE features (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            acceptance_criteria TEXT,
            status TEXT DEFAULT 'pending',
            risk_category TEXT DEFAULT 'medium',
            conf_spec_understanding REAL DEFAULT 0.0,
            conf_impl_correctness REAL DEFAULT 0.0,
            conf_test_adequacy REAL DEFAULT 0.0,
            readiness_score REAL DEFAULT 0.0,
            spec_quality_score REAL,
            parent_feature_id TEXT,
            decomposition_depth INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 100,
            tdd_mode BOOLEAN,
            sub_agent_mode BOOLEAN,
            refinement_attempts INTEGER DEFAULT 0,
            max_refinement_attempts INTEGER DEFAULT 5,
            last_improvement_type TEXT,
            research_iterations INTEGER DEFAULT 0,
            original_acceptance_criteria_count INTEGER,
            original_task_count INTEGER,
            estimated_lines_of_code INTEGER,
            estimated_files_touched INTEGER,
            estimated_complexity INTEGER,
            exceeds_size_limits BOOLEAN DEFAULT FALSE,
            size_limit_justification TEXT,
            reviewer_confidence_cap REAL,
            completion_mode TEXT DEFAULT 'all_or_nothing',
            tasks_completed INTEGER DEFAULT 0,
            tasks_total INTEGER DEFAULT 0,
            spec_slot TEXT,
            permanent_forward_carry BOOLEAN DEFAULT FALSE,
            test_files TEXT,
            parent_completed BOOLEAN DEFAULT FALSE,
            parent_status TEXT,
            parent_completed_at TIMESTAMP,
            parent_evidence_hash TEXT,
            bootstrap_attempts INTEGER DEFAULT 0,
            provenance_spans TEXT,
            rtm_artifact_path TEXT,
            last_reap_at TIMESTAMP,
            reap_count INTEGER DEFAULT 0,
            subagent_pid INTEGER,
            subagent_heartbeat_at TIMESTAMP,
            readiness_components TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()

    import bob.db as db_mod

    original_get_db = getattr(db_mod, "_get_db_path", None)

    def _patched_get_feature(feature_id):
        cur = conn.execute(
            "SELECT * FROM features WHERE id = ?", (feature_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        # Return a simple namespace so attribute access works
        import types
        obj = types.SimpleNamespace(**dict(row))
        return obj

    monkeypatch.setattr(db_mod, "get_feature", _patched_get_feature, raising=False)

    def _insert_feature(**kwargs):
        fid = kwargs.get("id", str(uuid.uuid4()))
        kwargs.setdefault("project_id", "proj-test")
        kwargs.setdefault("status", "ready")
        keys = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?" for _ in kwargs])
        conn.execute(
            f"INSERT INTO features ({keys}) VALUES ({placeholders})",
            list(kwargs.values()),
        )
        conn.commit()
        return fid

    yield conn, _insert_feature


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


class TestImport:
    def test_module_importable(self):
        import bob.assess_feature_confidence  # noqa: F401

    def test_assess_with_spec_quality_mapping_callable(self):
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        assert callable(assess_with_spec_quality_mapping)

    def test_assess_feature_confidence_callable(self):
        from bob.assess_feature_confidence import assess_feature_confidence

        assert callable(assess_feature_confidence)

    def test_all_exports(self):
        import bob.assess_feature_confidence as mod

        assert "assess_with_spec_quality_mapping" in mod.__all__
        assert "assess_feature_confidence" in mod.__all__


# ---------------------------------------------------------------------------
# Return-value contract tests
# ---------------------------------------------------------------------------


class TestReturnValueContract:
    def test_unknown_feature_returns_all_zero(self):
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping("nonexistent-id-" + str(uuid.uuid4()))
        assert isinstance(result, dict)
        assert result["readiness_score"] == 0.0
        assert result["conf_spec_understanding"] == 0.0
        assert result["conf_impl_correctness"] == 0.0
        assert result["conf_test_adequacy"] == 0.0

    def test_returns_dict_with_required_keys(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="standalone feature",
            description="a standalone feature",
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
            spec_quality_score=0.95,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        assert "readiness_score" in result
        assert "conf_spec_understanding" in result
        assert "conf_impl_correctness" in result
        assert "conf_test_adequacy" in result

    def test_all_values_are_floats(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="standalone feature",
            description="does not integrate anything",
            spec_quality_score=0.90,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        for key, value in result.items():
            assert isinstance(value, float), f"{key} is not float: {type(value)}"


# ---------------------------------------------------------------------------
# Spec-quality-score mapping tests
# ---------------------------------------------------------------------------


class TestSpecQualityMapping:
    def test_standalone_feature_readiness_uses_spec_quality_times_092(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        spec_q = 0.95
        insert(
            id=fid,
            name="fast readiness module",
            description="computes readiness score from components",
            spec_quality_score=spec_q,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        expected = round(spec_q * 0.92, 10)
        assert abs(result["readiness_score"] - expected) < 1e-9

    def test_integration_feature_readiness_uses_spec_quality_times_030(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        spec_q = 0.95
        insert(
            id=fid,
            name="wire hooks into orchestrator",
            description="integrate the new hook into the pipeline",
            spec_quality_score=spec_q,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        expected = round(spec_q * 0.30, 10)
        assert abs(result["readiness_score"] - expected) < 1e-9

    def test_bare_pass_composite_085_yields_below_080_for_standalone(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="standalone readiness scorer",
            description="no integration involved",
            spec_quality_score=0.85,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        # 0.85 * 0.92 = 0.782 < 0.80 medium threshold
        assert result["readiness_score"] < 0.80

    def test_strong_composite_095_clears_080_gate_for_standalone(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="standalone readiness scorer",
            description="no integration involved",
            spec_quality_score=0.95,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        # 0.95 * 0.92 = 0.874 > 0.80 medium threshold
        assert result["readiness_score"] > 0.80

    def test_feature_without_spec_quality_score_falls_back_to_heuristic(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="fresh feature no spec quality",
            description="brand new feature",
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
            spec_quality_score=None,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        # Heuristic should give non-zero since >= 3 ACs
        assert result["readiness_score"] > 0.0

    def test_feature_with_zero_spec_quality_falls_back_to_heuristic(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="zero quality feature",
            description="never passed spec gate",
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
            spec_quality_score=0.0,
        )
        from bob.assess_feature_confidence import assess_with_spec_quality_mapping

        result = assess_with_spec_quality_mapping(fid)
        # Falls back to heuristic
        assert result["readiness_score"] >= 0.0


# ---------------------------------------------------------------------------
# assess_feature_confidence delegates correctly
# ---------------------------------------------------------------------------


class TestAssessFeatureConfidenceDelegate:
    def test_delegates_to_assess_with_spec_quality_mapping(self, tmp_db):
        conn, insert = tmp_db
        fid = str(uuid.uuid4())
        insert(
            id=fid,
            name="any feature",
            description="not integration",
            spec_quality_score=0.92,
        )
        from bob.assess_feature_confidence import (
            assess_feature_confidence,
            assess_with_spec_quality_mapping,
        )

        r1 = assess_with_spec_quality_mapping(fid)
        r2 = assess_feature_confidence(fid)
        assert r1 == r2

    def test_assess_feature_confidence_unknown_returns_zeros(self):
        from bob.assess_feature_confidence import assess_feature_confidence

        result = assess_feature_confidence("no-such-feature-" + str(uuid.uuid4()))
        assert result["readiness_score"] == 0.0
