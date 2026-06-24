"""Tests for F026: Feature size limit checking (LOC, files, complexity).

Tests check_feature_size() function which evaluates whether a feature
exceeds size limits based on estimated_lines_of_code (>500),
estimated_files_touched (>5), and estimated_complexity (>8).
"""

import pytest

from bob import db


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    """Set up a temporary database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "get_database_path", lambda: db_path)
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture
def project():
    """Create a test project."""
    return db.create_project(name="test-project", workspace_path="/tmp/test")


@pytest.fixture
def feature(project):
    """Create a basic feature with no size estimates set."""
    return db.create_feature(
        project_id=project.id,
        name="Test Feature",
    )


# ============================================================
# Step 1: check_feature_size() function exists and works
# ============================================================


class TestCheckFeatureSizeFunction:
    """Test that check_feature_size() function exists and returns expected structure."""

    def test_returns_dict(self, feature):
        """check_feature_size() returns a dict."""
        result = db.check_feature_size(feature.id)
        assert isinstance(result, dict)

    def test_returns_none_for_nonexistent_feature(self):
        """Returns None for a feature that doesn't exist."""
        result = db.check_feature_size("nonexistent-id")
        assert result is None

    def test_result_has_expected_keys(self, feature):
        """Result dict has the expected keys."""
        result = db.check_feature_size(feature.id)
        assert "exceeds_size_limits" in result
        assert "violations" in result
        assert "estimated_lines_of_code" in result
        assert "estimated_files_touched" in result
        assert "estimated_complexity" in result

    def test_no_estimates_does_not_exceed(self, feature):
        """Feature with no estimates does not exceed size limits."""
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False
        assert result["violations"] == []


# ============================================================
# Step 2: Check estimated_lines_of_code > 500
# ============================================================


class TestLinesOfCodeLimit:
    """Test LOC limit checking (threshold: 500)."""

    def test_500_loc_does_not_exceed(self, feature):
        """Exactly 500 LOC does not exceed the limit."""
        db.update_feature(feature.id, estimated_lines_of_code=500)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False
        assert "estimated_lines_of_code" not in [v["field"] for v in result["violations"]]

    def test_501_loc_exceeds(self, feature):
        """501 LOC exceeds the limit."""
        db.update_feature(feature.id, estimated_lines_of_code=501)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is True
        violation_fields = [v["field"] for v in result["violations"]]
        assert "estimated_lines_of_code" in violation_fields

    def test_1000_loc_exceeds(self, feature):
        """1000 LOC exceeds the limit."""
        db.update_feature(feature.id, estimated_lines_of_code=1000)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is True

    def test_100_loc_does_not_exceed(self, feature):
        """100 LOC does not exceed the limit."""
        db.update_feature(feature.id, estimated_lines_of_code=100)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False


# ============================================================
# Step 3: Check estimated_files_touched > 5
# ============================================================


class TestFilesTouchedLimit:
    """Test files touched limit checking (threshold: 5)."""

    def test_5_files_does_not_exceed(self, feature):
        """Exactly 5 files does not exceed the limit."""
        db.update_feature(feature.id, estimated_files_touched=5)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False

    def test_6_files_exceeds(self, feature):
        """6 files exceeds the limit."""
        db.update_feature(feature.id, estimated_files_touched=6)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is True
        violation_fields = [v["field"] for v in result["violations"]]
        assert "estimated_files_touched" in violation_fields

    def test_3_files_does_not_exceed(self, feature):
        """3 files does not exceed the limit."""
        db.update_feature(feature.id, estimated_files_touched=3)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False


# ============================================================
# Step 4: Check estimated_complexity > 8
# ============================================================


class TestComplexityLimit:
    """Test complexity limit checking (threshold: 8)."""

    def test_8_complexity_does_not_exceed(self, feature):
        """Exactly 8 complexity does not exceed the limit."""
        db.update_feature(feature.id, estimated_complexity=8)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False

    def test_9_complexity_exceeds(self, feature):
        """9 complexity exceeds the limit."""
        db.update_feature(feature.id, estimated_complexity=9)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is True
        violation_fields = [v["field"] for v in result["violations"]]
        assert "estimated_complexity" in violation_fields

    def test_5_complexity_does_not_exceed(self, feature):
        """5 complexity does not exceed the limit."""
        db.update_feature(feature.id, estimated_complexity=5)
        result = db.check_feature_size(feature.id)
        assert result["exceeds_size_limits"] is False


# ============================================================
# Step 5: exceeds_size_limits flag persisted appropriately
# ============================================================


class TestExceedsSizeLimitsPersistence:
    """Test that exceeds_size_limits flag is persisted to the database."""

    def test_flag_set_true_when_exceeding(self, feature):
        """exceeds_size_limits is persisted as True when limits are exceeded."""
        db.update_feature(feature.id, estimated_lines_of_code=600)
        db.check_feature_size(feature.id)
        updated = db.get_feature(feature.id)
        assert updated.exceeds_size_limits is True

    def test_flag_set_false_when_within_limits(self, feature):
        """exceeds_size_limits is persisted as False when within limits."""
        db.update_feature(feature.id, estimated_lines_of_code=100)
        db.check_feature_size(feature.id)
        updated = db.get_feature(feature.id)
        assert updated.exceeds_size_limits is False

    def test_justification_stored_when_exceeding(self, feature):
        """size_limit_justification is stored when limits are exceeded."""
        db.update_feature(feature.id, estimated_lines_of_code=600)
        db.check_feature_size(feature.id)
        updated = db.get_feature(feature.id)
        assert updated.size_limit_justification is not None
        assert "estimated_lines_of_code" in updated.size_limit_justification

    def test_justification_cleared_when_within_limits(self, feature):
        """size_limit_justification is cleared when within limits."""
        # First set it to exceeding
        db.update_feature(feature.id, estimated_lines_of_code=600)
        db.check_feature_size(feature.id)
        # Then bring it back within limits
        db.update_feature(feature.id, estimated_lines_of_code=100)
        db.check_feature_size(feature.id)
        updated = db.get_feature(feature.id)
        assert updated.size_limit_justification is None

    def test_multiple_violations_in_justification(self, feature):
        """size_limit_justification mentions all violated limits."""
        db.update_feature(
            feature.id,
            estimated_lines_of_code=600,
            estimated_files_touched=10,
            estimated_complexity=9,
        )
        db.check_feature_size(feature.id)
        updated = db.get_feature(feature.id)
        assert "estimated_lines_of_code" in updated.size_limit_justification
        assert "estimated_files_touched" in updated.size_limit_justification
        assert "estimated_complexity" in updated.size_limit_justification


# ============================================================
# Step 6: Create oversized feature and verify flag is set
# ============================================================


class TestOversizedFeatureEndToEnd:
    """End-to-end test: create an oversized feature and verify the flag."""

    def test_oversized_feature_all_limits_exceeded(self, project):
        """Create a feature exceeding all limits and verify flag is set."""
        feat = db.create_feature(
            project_id=project.id,
            name="Giant Feature",
            description="This feature is way too big",
        )
        db.update_feature(
            feat.id,
            estimated_lines_of_code=1000,
            estimated_files_touched=15,
            estimated_complexity=10,
        )
        result = db.check_feature_size(feat.id)

        assert result["exceeds_size_limits"] is True
        assert len(result["violations"]) == 3

        # Verify persisted in DB
        updated = db.get_feature(feat.id)
        assert updated.exceeds_size_limits is True
        assert updated.size_limit_justification is not None

    def test_normal_feature_within_limits(self, project):
        """Create a normal-sized feature and verify flag is not set."""
        feat = db.create_feature(
            project_id=project.id,
            name="Small Feature",
        )
        db.update_feature(
            feat.id,
            estimated_lines_of_code=200,
            estimated_files_touched=3,
            estimated_complexity=5,
        )
        result = db.check_feature_size(feat.id)

        assert result["exceeds_size_limits"] is False
        assert len(result["violations"]) == 0

        updated = db.get_feature(feat.id)
        assert updated.exceeds_size_limits is False

    def test_single_limit_exceeded(self, project):
        """Feature exceeding only one limit still triggers the flag."""
        feat = db.create_feature(
            project_id=project.id,
            name="Complex Feature",
        )
        db.update_feature(
            feat.id,
            estimated_lines_of_code=100,
            estimated_files_touched=2,
            estimated_complexity=9,
        )
        result = db.check_feature_size(feat.id)

        assert result["exceeds_size_limits"] is True
        assert len(result["violations"]) == 1
        assert result["violations"][0]["field"] == "estimated_complexity"
