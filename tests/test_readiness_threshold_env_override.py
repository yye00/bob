"""Tests for the env-overridable readiness-claim threshold
(9ec1f44d-8e45-4441-859f-5ed30c83f484).

When BOB_READINESS_THRESHOLD is set to a float in [0,1], it REPLACES the
per-risk thresholds with a single floor for all risk categories in
claim_next_ready_feature. This unsticks the F-R7-564 readiness deadlock where
spec_quality_score is absent and readiness falls below the 0.80 medium gate.
"""

from __future__ import annotations

import pytest

from bob import db as bob_db
from bob.orchestrator.feature_claim import (
    claim_next_ready_feature,
    resolve_readiness_override,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB_READINESS_THRESHOLD", raising=False)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_readiness.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_file))
    from bob.db import init_database

    init_database(db_path=db_file)
    return db_file


@pytest.fixture()
def project_id(tmp_db):
    project = bob_db.create_project(
        name="Test Project",
        workspace_path="/tmp/test-workspace",
    )
    return project.id


def _make_feature(project_id, name, readiness, risk="medium", priority=100):
    feature = bob_db.create_feature(
        project_id=project_id,
        name=name,
        status="ready",
        priority=priority,
    )
    bob_db.update_feature(
        feature.id,
        readiness_score=readiness,
        risk_category=risk,
    )
    return feature.id


class TestResolveReadinessOverride:
    def test_unset_returns_none(self):
        assert resolve_readiness_override() is None

    def test_empty_returns_none(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": ""}) is None

    def test_valid_float_returned(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "0.5"}) == 0.5

    def test_valid_zero(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "0"}) == 0.0

    def test_valid_one(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "1"}) == 1.0

    def test_out_of_range_high_ignored(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "1.5"}) is None

    def test_out_of_range_negative_ignored(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "-0.2"}) is None

    def test_malformed_ignored(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "abc"}) is None


class TestOverrideAppliedToClaim:
    def test_default_threshold_blocks_subthreshold_feature(self, project_id):
        """A medium feature at 0.56 sits below the 0.80 gate and is not claimed."""
        _make_feature(project_id, "stuck", readiness=0.56, risk="medium")
        result = claim_next_ready_feature(project_id=project_id, worker_id="w1")
        assert result is None

    def test_override_unsticks_subthreshold_feature(self, project_id, monkeypatch):
        """With BOB_READINESS_THRESHOLD=0.5 the 0.56 feature becomes claimable."""
        fid = _make_feature(project_id, "stuck", readiness=0.56, risk="medium")
        monkeypatch.setenv("BOB_READINESS_THRESHOLD", "0.5")
        result = claim_next_ready_feature(project_id=project_id, worker_id="w1")
        assert result is not None
        assert result.id == fid
        assert result.status == "executing"

    def test_override_applies_to_all_risk_categories(self, project_id, monkeypatch):
        """A single floor replaces per-risk thresholds — a critical at 0.60 claims."""
        fid = _make_feature(project_id, "crit", readiness=0.60, risk="critical")
        monkeypatch.setenv("BOB_READINESS_THRESHOLD", "0.5")
        result = claim_next_ready_feature(project_id=project_id, worker_id="w1")
        assert result is not None
        assert result.id == fid

    def test_override_read_lazily_per_claim(self, project_id, monkeypatch):
        """Setting the override after a failed claim unsticks a later claim."""
        _make_feature(project_id, "stuck", readiness=0.56, risk="medium")
        assert claim_next_ready_feature(project_id=project_id, worker_id="w1") is None
        monkeypatch.setenv("BOB_READINESS_THRESHOLD", "0.5")
        assert claim_next_ready_feature(project_id=project_id, worker_id="w1") is not None
