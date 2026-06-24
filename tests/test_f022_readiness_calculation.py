"""Tests for F022: Feature readiness calculation based on risk category thresholds."""

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
def project_id(db_path):
    """Create a project and return its ID for use as a foreign key."""
    from bob.db import create_project

    project = create_project(
        name="Readiness Test Project",
        workspace_path="/tmp/test-readiness",
    )
    return project.id


# ============================================================
# Step 1: calculate_readiness() function exists
# ============================================================


class TestCalculateReadinessExists:
    """calculate_readiness() is importable and callable."""

    def test_calculate_readiness_importable(self):
        from bob.db import calculate_readiness

        assert callable(calculate_readiness)

    def test_calculate_readiness_returns_dict(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="Basic Feature",
            risk_category="medium",
        )
        result = calculate_readiness(feature.id)
        assert isinstance(result, dict)

    def test_calculate_readiness_has_required_keys(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="Keys Feature",
            risk_category="medium",
        )
        result = calculate_readiness(feature.id)
        assert "readiness_score" in result
        assert "is_ready" in result
        assert "threshold" in result
        assert "components" in result

    def test_calculate_readiness_nonexistent_feature_returns_none(self, db_path):
        from bob.db import calculate_readiness

        result = calculate_readiness("nonexistent-feature-id")
        assert result is None


# ============================================================
# Step 2: Threshold lookup by risk category
# ============================================================


class TestThresholdLookup:
    """Correct thresholds are applied based on risk category."""

    def test_low_risk_threshold_is_070(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="Low Risk Feature",
            risk_category="low",
        )
        result = calculate_readiness(feature.id)
        assert result["threshold"] == 0.70

    def test_medium_risk_threshold_is_080(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="Medium Risk Feature",
            risk_category="medium",
        )
        result = calculate_readiness(feature.id)
        assert result["threshold"] == 0.80

    def test_high_risk_threshold_is_090(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="High Risk Feature",
            risk_category="high",
        )
        result = calculate_readiness(feature.id)
        assert result["threshold"] == 0.90

    def test_critical_risk_threshold_is_095(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="Critical Risk Feature",
            risk_category="critical",
        )
        result = calculate_readiness(feature.id)
        assert result["threshold"] == 0.95


# ============================================================
# Step 3: Check all components (spec, impl, test)
# ============================================================


class TestReadinessComponents:
    """Readiness calculation uses all three confidence components."""

    def test_components_included_in_result(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Components Feature",
            risk_category="medium",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.9,
        )
        result = calculate_readiness(feature.id)
        components = result["components"]
        assert "spec_understanding" in components
        assert "impl_correctness" in components
        assert "test_adequacy" in components

    def test_components_reflect_feature_confidences(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Reflect Feature",
            risk_category="low",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.8,
            conf_test_adequacy=0.7,
        )
        result = calculate_readiness(feature.id)
        components = result["components"]
        assert components["spec_understanding"] == 0.9
        assert components["impl_correctness"] == 0.8
        assert components["test_adequacy"] == 0.7

    def test_readiness_score_is_average_of_components(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Average Feature",
            risk_category="medium",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.8,
            conf_test_adequacy=0.7,
        )
        result = calculate_readiness(feature.id)
        expected = (0.9 + 0.8 + 0.7) / 3.0
        assert abs(result["readiness_score"] - expected) < 0.001

    def test_readiness_score_zero_when_all_zero(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature

        feature = create_feature(
            project_id=project_id,
            name="Zero Feature",
            risk_category="medium",
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 0.0

    def test_readiness_score_one_when_all_one(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Perfect Feature",
            risk_category="medium",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=1.0,
            conf_impl_correctness=1.0,
            conf_test_adequacy=1.0,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 1.0


# ============================================================
# Step 4: Low risk with 0.75 readiness should be ready
# ============================================================


class TestLowRiskReady:
    """Feature with low risk and 0.75 readiness should be ready."""

    def test_low_risk_075_readiness_is_ready(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Low Risk Ready",
            risk_category="low",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.75,
            conf_impl_correctness=0.75,
            conf_test_adequacy=0.75,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 0.75
        assert result["is_ready"] is True

    def test_low_risk_exactly_at_threshold_is_ready(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Low Risk Exact",
            risk_category="low",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.70,
            conf_impl_correctness=0.70,
            conf_test_adequacy=0.70,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 0.70
        assert result["is_ready"] is True

    def test_low_risk_below_threshold_not_ready(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Low Risk Not Ready",
            risk_category="low",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.60,
            conf_impl_correctness=0.60,
            conf_test_adequacy=0.60,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 0.60
        assert result["is_ready"] is False


# ============================================================
# Step 5: Critical risk with 0.90 readiness should NOT be ready
# ============================================================


class TestCriticalRiskNotReady:
    """Feature with critical risk and 0.90 readiness should NOT be ready."""

    def test_critical_risk_090_readiness_not_ready(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Critical Not Ready",
            risk_category="critical",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.90,
            conf_impl_correctness=0.90,
            conf_test_adequacy=0.90,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 0.90
        assert result["is_ready"] is False

    def test_critical_risk_exactly_at_threshold_is_ready(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Critical Exact",
            risk_category="critical",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.95,
            conf_impl_correctness=0.95,
            conf_test_adequacy=0.95,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 0.95
        assert result["is_ready"] is True

    def test_critical_risk_above_threshold_is_ready(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Critical Above",
            risk_category="critical",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=1.0,
            conf_impl_correctness=1.0,
            conf_test_adequacy=1.0,
        )
        result = calculate_readiness(feature.id)
        assert result["readiness_score"] == 1.0
        assert result["is_ready"] is True


# ============================================================
# Step 6: Verify readiness_score is stored in database
# ============================================================


class TestReadinessStoredInDatabase:
    """Readiness score is persisted to the features table."""

    def test_readiness_score_stored_after_calculation(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, get_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Stored Feature",
            risk_category="medium",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.80,
            conf_test_adequacy=0.90,
        )
        result = calculate_readiness(feature.id)

        fetched = get_feature(feature.id)
        assert fetched.readiness_score == result["readiness_score"]

    def test_readiness_components_stored_as_json(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, get_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="JSON Components",
            risk_category="low",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.8,
            conf_test_adequacy=0.7,
        )
        calculate_readiness(feature.id)

        fetched = get_feature(feature.id)
        assert fetched.readiness_components is not None
        components = json.loads(fetched.readiness_components)
        assert components["spec_understanding"] == 0.9
        assert components["impl_correctness"] == 0.8
        assert components["test_adequacy"] == 0.7

    def test_readiness_score_stored_in_raw_database(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Raw DB Feature",
            risk_category="high",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
        )
        result = calculate_readiness(feature.id)

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT readiness_score, readiness_components FROM features WHERE id = ?",
                (feature.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert abs(row[0] - result["readiness_score"]) < 0.001
            assert row[1] is not None
            components = json.loads(row[1])
            assert "spec_understanding" in components
        finally:
            conn.close()

    def test_readiness_updated_on_recalculation(self, db_path, project_id):
        from bob.db import calculate_readiness, create_feature, get_feature, update_feature

        feature = create_feature(
            project_id=project_id,
            name="Recalc Feature",
            risk_category="medium",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.5,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.5,
        )
        result1 = calculate_readiness(feature.id)
        assert result1["readiness_score"] == 0.5
        assert result1["is_ready"] is False

        update_feature(
            feature.id,
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
        )
        result2 = calculate_readiness(feature.id)
        assert result2["readiness_score"] == 0.9
        assert result2["is_ready"] is True

        fetched = get_feature(feature.id)
        assert fetched.readiness_score == 0.9
