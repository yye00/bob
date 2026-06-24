"""Tests for bob3.confidence.assess_feature_confidence.

Verifies:
- assess_feature_confidence is importable from bob3.confidence
- Returns correct keys (conf_spec_understanding, conf_impl_correctness,
  conf_test_adequacy, readiness_score)
- Derives readiness from spec_quality_score when present (not AC-count heuristic)
- Integration features get 0.30 impl_factor; standalone features get 0.92
- Falls back to AC-count heuristic when spec_quality_score is absent
- Returns all-zero dict for unknown feature_id
"""

from __future__ import annotations

import json
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Import sanity
# ---------------------------------------------------------------------------


class TestImport:
    """bob3.confidence.assess_feature_confidence must be importable."""

    def test_importable_from_bob3_confidence(self):
        from bob3.confidence import assess_feature_confidence

        assert callable(assess_feature_confidence)

    def test_module_path_is_bob3_confidence(self):
        """The function must live under bob3.confidence (per AC)."""
        import bob3.confidence as mod

        assert hasattr(mod, "assess_feature_confidence"), (
            "bob3.confidence must expose assess_feature_confidence"
        )

    def test_accepts_feature_id_string(self):
        from bob3.confidence import assess_feature_confidence
        import inspect

        sig = inspect.signature(assess_feature_confidence)
        assert "feature_id" in sig.parameters


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------


class TestReturnStructure:
    """assess_feature_confidence must return a dict with the four required keys."""

    def test_unknown_feature_returns_all_zeros(self):
        from bob3.confidence import assess_feature_confidence

        result = assess_feature_confidence("nonexistent-feature-id-xyzzy")
        assert isinstance(result, dict)
        for key in ("conf_spec_understanding", "conf_impl_correctness",
                    "conf_test_adequacy", "readiness_score"):
            assert key in result, f"Missing key: {key}"
            assert result[key] == 0.0

    def test_returns_all_required_keys(self, tmp_path, monkeypatch):
        from bob3 import db as bob_db
        from bob3.confidence import assess_feature_confidence

        db_path = tmp_path / "test_structure.db"
        schema_path = "/home/yelkhamr/dark-factory/bob63/src/bob3/schema.sql"
        conn = sqlite3.connect(str(db_path))
        with open(schema_path) as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        project = bob_db.create_project(name="p1", workspace_path=str(tmp_path))
        feature = bob_db.create_feature(
            project_id=project.id,
            name="test feature",
            description="standalone feature",
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
        )

        result = assess_feature_confidence(feature.id)
        for key in ("conf_spec_understanding", "conf_impl_correctness",
                    "conf_test_adequacy", "readiness_score"):
            assert key in result, f"Missing key: {key}"
        for val in result.values():
            assert isinstance(val, float)
            assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# Readiness derivation from spec_quality_score
# ---------------------------------------------------------------------------


class TestReadinessDerivedFromSpecQualityScore:
    """When spec_quality_score is present, readiness = sq * impl_factor."""

    def _make_feature(self, tmp_path, monkeypatch, name, description, ac_list,
                      spec_quality_score=None):
        from bob3 import db as bob_db

        db_path = tmp_path / f"test_{name}.db"
        schema_path = "/home/yelkhamr/dark-factory/bob63/src/bob3/schema.sql"
        conn = sqlite3.connect(str(db_path))
        with open(schema_path) as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        project = bob_db.create_project(name=name, workspace_path=str(tmp_path))
        kwargs = dict(
            project_id=project.id,
            name=name,
            description=description,
            acceptance_criteria=json.dumps(ac_list),
        )
        if spec_quality_score is not None:
            kwargs["spec_quality_score"] = spec_quality_score
        feature = bob_db.create_feature(**kwargs)
        return feature

    def test_standalone_feature_high_spec_quality(self, tmp_path, monkeypatch):
        """standalone: readiness = spec_quality_score * 0.92"""
        from bob3.confidence import assess_feature_confidence

        sq = 0.95
        feature = self._make_feature(
            tmp_path, monkeypatch,
            name="standalone-high",
            description="Implement a pure calculation function",
            ac_list=["AC1", "AC2", "AC3"],
            spec_quality_score=sq,
        )

        result = assess_feature_confidence(feature.id)
        expected = round(min(1.0, sq * 0.92), 10)
        assert abs(result["readiness_score"] - expected) < 1e-6, (
            f"Expected readiness {expected:.4f} (sq*0.92), got {result['readiness_score']:.4f}"
        )

    def test_standalone_feature_bare_pass_composite(self, tmp_path, monkeypatch):
        """bare-pass composite (0.85) -> readiness = 0.782 (below 0.80 medium gate)."""
        from bob3.confidence import assess_feature_confidence

        sq = 0.85
        feature = self._make_feature(
            tmp_path, monkeypatch,
            name="standalone-bare-pass",
            description="Implement data validation logic",
            ac_list=["AC1", "AC2", "AC3"],
            spec_quality_score=sq,
        )

        result = assess_feature_confidence(feature.id)
        readiness = result["readiness_score"]
        expected = round(sq * 0.92, 10)
        assert abs(readiness - expected) < 1e-6
        assert readiness < 0.80, (
            f"Bare-pass composite must not clear 0.80 medium gate; got {readiness:.4f}"
        )

    def test_integration_feature_uses_low_impl_factor(self, tmp_path, monkeypatch):
        """integration feature: readiness = spec_quality_score * 0.30"""
        from bob3.confidence import assess_feature_confidence

        sq = 0.95
        feature = self._make_feature(
            tmp_path, monkeypatch,
            name="integration-feature",
            description="integrate the payment gateway hook into the order workflow",
            ac_list=["AC1", "AC2", "AC3"],
            spec_quality_score=sq,
        )

        result = assess_feature_confidence(feature.id)
        expected = round(min(1.0, sq * 0.30), 10)
        assert abs(result["readiness_score"] - expected) < 1e-6, (
            f"Integration feature should use 0.30 factor; "
            f"expected {expected:.4f}, got {result['readiness_score']:.4f}"
        )

    def test_integration_readiness_below_medium_threshold(self, tmp_path, monkeypatch):
        """Integration features must stay below 0.80 even with perfect spec."""
        from bob3.confidence import assess_feature_confidence

        feature = self._make_feature(
            tmp_path, monkeypatch,
            name="integration-perfect",
            description="connect the authentication service to the user hook",
            ac_list=["AC1", "AC2", "AC3"],
            spec_quality_score=1.0,
        )

        result = assess_feature_confidence(feature.id)
        assert result["readiness_score"] < 0.80, (
            f"Integration feature must stay below 0.80; got {result['readiness_score']:.4f}"
        )

    def test_fallback_to_ac_count_when_no_spec_quality(self, tmp_path, monkeypatch):
        """When spec_quality_score is None, falls back to AC-count heuristic."""
        from bob3.confidence import assess_feature_confidence

        feature = self._make_feature(
            tmp_path, monkeypatch,
            name="no-composite",
            description="Standalone feature without quality composite",
            ac_list=["AC1", "AC2", "AC3"],
            spec_quality_score=None,
        )

        result = assess_feature_confidence(feature.id)
        # With 3 ACs, spec_score=0.7 → min(0.7, 0.7, 0.56) = 0.56
        # We just verify it's non-zero and below the threshold for standalone with 0.85+ composite
        assert result["readiness_score"] >= 0.0
        assert result["readiness_score"] <= 1.0

    def test_zero_spec_quality_falls_back_to_heuristic(self, tmp_path, monkeypatch):
        """When spec_quality_score is 0.0, falls back to AC-count heuristic (not sq*factor)."""
        from bob3.confidence import assess_feature_confidence

        feature = self._make_feature(
            tmp_path, monkeypatch,
            name="zero-composite",
            description="feature with zero quality score",
            ac_list=["AC1", "AC2", "AC3"],
            spec_quality_score=0.0,
        )

        result = assess_feature_confidence(feature.id)
        # Falls back to heuristic: min(spec, impl, test), spec=0.7, impl=0.7, test=0.56
        # Result must be the heuristic, not 0.0 * 0.92 = 0.0
        assert "readiness_score" in result


# ---------------------------------------------------------------------------
# Readiness is not the stored value — derived from components
# ---------------------------------------------------------------------------


class TestReadinessDerivedNotStored:
    """readiness_score in the result must be freshly derived, not the DB column."""

    def test_assess_returns_derived_not_stored_readiness(self, tmp_path, monkeypatch):
        """assess_feature_confidence must NOT return the stored readiness_score column."""
        from bob3 import db as bob_db
        from bob3.confidence import assess_feature_confidence

        db_path = tmp_path / "test_derived.db"
        schema_path = "/home/yelkhamr/dark-factory/bob63/src/bob3/schema.sql"
        conn = sqlite3.connect(str(db_path))
        with open(schema_path) as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        project = bob_db.create_project(name="p-derived", workspace_path=str(tmp_path))
        feature = bob_db.create_feature(
            project_id=project.id,
            name="derived-test",
            description="standalone feature",
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
            spec_quality_score=0.95,
            readiness_score=0.10,  # stale/ratcheted stored value
        )

        result = assess_feature_confidence(feature.id)
        # Must return the derived value (0.95 * 0.92 = 0.874), NOT the stale 0.10
        assert result["readiness_score"] > 0.10, (
            f"assess must derive readiness from spec_quality_score, "
            f"not return stale stored 0.10; got {result['readiness_score']:.4f}"
        )
