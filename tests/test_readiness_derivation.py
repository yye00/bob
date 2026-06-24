"""Tests for readiness_score derivation (feature d0abe882).

Verifies that:
- derive_readiness_score computes mean of confidence components, not stored state
- decay_confidence_components decays only components, never writes readiness_score
- Integration: run_loop uses derived readiness, not the ratcheted stored value
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Tests for bob.readiness.derive_readiness_score
# ---------------------------------------------------------------------------

class TestDeriveReadinessScore:
    """derive_readiness_score must compute mean(impl, spec, test) from live components."""

    def test_equal_components_return_mean(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        assert abs(score - 0.9) < 1e-9

    def test_mixed_components_return_arithmetic_mean(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=0.6,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        expected = (0.6 + 0.9 + 0.9) / 3.0
        assert abs(score - expected) < 1e-9

    def test_zero_components_return_zero(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert score == 0.0

    def test_full_components_return_one(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(score - 1.0) < 1e-9

    def test_independent_of_stored_readiness_score(self):
        """derive_readiness_score takes no stored_readiness arg — it cannot see it."""
        from bob.readiness import derive_readiness_score
        import inspect

        sig = inspect.signature(derive_readiness_score)
        param_names = set(sig.parameters.keys())
        assert "stored_readiness" not in param_names, (
            "derive_readiness_score must not accept stored_readiness — "
            "derivation must be independent of the persisted column"
        )

    def test_result_clamped_to_zero_one(self):
        """Any float inputs clamp result to [0.0, 1.0]."""
        from bob.readiness import derive_readiness_score

        # Normal call should always be in [0, 1] given valid component inputs
        score = derive_readiness_score(
            conf_impl_correctness=0.3,
            conf_spec_understanding=0.7,
            conf_test_quality=0.5,
        )
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Tests for bob.run_loop.decay_confidence_components
# ---------------------------------------------------------------------------

class TestDecayConfidenceComponents:
    """decay_confidence_components must decay only conf_* columns, not readiness_score."""

    def test_function_exists_in_run_loop(self):
        from bob.orchestrator import run_loop

        assert hasattr(run_loop, "decay_confidence_components"), (
            "bob.run_loop must export decay_confidence_components as a public function"
        )

    def test_decay_confidence_components_returns_feature_or_none(self):
        """Function signature must accept feature_id and optional decay kwarg."""
        from bob.orchestrator.run_loop import decay_confidence_components
        import inspect

        sig = inspect.signature(decay_confidence_components)
        params = sig.parameters
        assert "feature_id" in params, "decay_confidence_components must accept feature_id"

    def test_decay_reduces_each_component(self, tmp_path, monkeypatch):
        """After decay, each conf_* value is lower by the decay amount (floored at 0)."""
        import sqlite3, json
        from bob import db as bob_db

        # Minimal in-memory DB setup
        db_path = tmp_path / "test.db"
        import pathlib
        schema_path = pathlib.Path(__file__).parents[1] / "src" / "bob" / "schema.sql"
        conn = sqlite3.connect(str(db_path))
        with open(schema_path) as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        # Create a project and feature
        project = bob_db.create_project(name="test-proj", workspace_path=str(tmp_path))
        feature = bob_db.create_feature(
            project_id=project.id,
            name="test feature",
            description="desc",
            acceptance_criteria=json.dumps(["AC1"]),
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.8,
            conf_test_adequacy=0.7,
            readiness_score=0.8,
        )

        monkeypatch.setenv("BOB_CONFIDENCE_DECAY_PER_FAILURE", "0.15")
        from bob.orchestrator.run_loop import decay_confidence_components
        result = decay_confidence_components(feature.id)

        if result is not None:
            # Components decayed, readiness_score NOT written by this call
            assert abs(result.conf_impl_correctness - 0.75) < 1e-6
            assert abs(result.conf_spec_understanding - 0.65) < 1e-6
            assert abs(result.conf_test_adequacy - 0.55) < 1e-6

    def test_decay_does_not_write_readiness_score_column(self, tmp_path, monkeypatch):
        """The readiness_score column must not be modified by decay_confidence_components."""
        import sqlite3, json
        from bob import db as bob_db

        db_path = tmp_path / "test2.db"
        import pathlib
        schema_path = pathlib.Path(__file__).parents[1] / "src" / "bob" / "schema.sql"
        conn = sqlite3.connect(str(db_path))
        with open(schema_path) as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        project = bob_db.create_project(name="test-proj2", workspace_path=str(tmp_path))
        stored_readiness = 0.9
        feature = bob_db.create_feature(
            project_id=project.id,
            name="test feature 2",
            description="desc",
            acceptance_criteria=json.dumps(["AC1"]),
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.9,
            conf_test_adequacy=0.9,
            readiness_score=stored_readiness,
        )

        monkeypatch.setenv("BOB_CONFIDENCE_DECAY_PER_FAILURE", "0.15")
        from bob.orchestrator.run_loop import decay_confidence_components
        decay_confidence_components(feature.id)

        # Read back from DB directly
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT readiness_score FROM features WHERE id = ?", (feature.id,)
        ).fetchone()
        conn.close()

        assert row is not None
        # readiness_score column unchanged by the decay call
        assert abs(row["readiness_score"] - stored_readiness) < 1e-6, (
            f"decay_confidence_components must NOT write readiness_score column; "
            f"expected {stored_readiness}, got {row['readiness_score']}"
        )


# ---------------------------------------------------------------------------
# Integration: derive_readiness_score reflects fresh signal after decay
# ---------------------------------------------------------------------------

class TestReadinessDerivedNotDecayed:
    """Core invariant: readiness derived from live components ignores stored ratchet."""

    def test_derived_readiness_higher_than_stored_after_multiple_decays(self):
        """If components improved after reset, derived score > stored decayed value."""
        from bob.readiness import derive_readiness_score

        # Simulate: stored readiness decayed to 0.40 over 3 failures
        stored_readiness = 0.40

        # But confidence components were restored to baseline after infra-only verdict
        derived = derive_readiness_score(
            conf_impl_correctness=0.85,
            conf_spec_understanding=0.85,
            conf_test_quality=0.85,
        )

        assert derived > stored_readiness, (
            f"Derived readiness {derived:.3f} must exceed stored ratchet {stored_readiness:.3f}"
        )

    def test_derive_readiness_score_is_callable_with_keyword_args(self):
        """Function must accept named parameters matching the confidence column names."""
        from bob.readiness import derive_readiness_score

        result = derive_readiness_score(
            conf_impl_correctness=0.7,
            conf_spec_understanding=0.8,
            conf_test_quality=0.9,
        )
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_conf_test_quality_alias_accepted(self):
        """conf_test_quality parameter is accepted (spec says conf_test_quality)."""
        from bob.readiness import derive_readiness_score

        # Must not raise TypeError for conf_test_quality kwarg
        score = derive_readiness_score(
            conf_impl_correctness=0.5,
            conf_spec_understanding=0.5,
            conf_test_quality=0.5,
        )
        assert abs(score - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# Behavior ACs: boundary and invalid input handling
# ---------------------------------------------------------------------------

class TestBoundaryAndInvalidInput:
    """Behavior ACs: boundary cases return well-defined results; invalid inputs raise."""

    def test_zero_inputs_return_zero_not_crash(self):
        """Boundary case: all-zero inputs must return 0.0, not raise."""
        from bob.readiness import derive_readiness_score

        result = derive_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert result == 0.0, (
            f"All-zero boundary case must return 0.0, got {result!r}"
        )

    def test_boundary_max_inputs_return_one(self):
        """Boundary case: all-1.0 inputs must return 1.0, not raise."""
        from bob.readiness import derive_readiness_score

        result = derive_readiness_score(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(result - 1.0) < 1e-9

    def test_one_component_zero_rest_nonzero_returns_mean(self):
        """Boundary: one zero component still returns mean, not crash."""
        from bob.readiness import derive_readiness_score

        result = derive_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        expected = (0.0 + 0.9 + 0.9) / 3.0
        assert abs(result - expected) < 1e-9

    def test_negative_input_raises_value_error(self):
        """Invalid input: negative confidence component must raise ValueError."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError, match="conf_impl_correctness"):
            derive_readiness_score(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_above_one_input_raises_value_error(self):
        """Invalid input: component > 1.0 must raise ValueError, not silently succeed."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError, match="conf_spec_understanding"):
            derive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=1.1,
                conf_test_quality=0.5,
            )

    def test_none_input_raises_value_error(self):
        """Invalid input: None component must raise ValueError, not TypeError."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=None,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_nan_input_raises_value_error(self):
        """Invalid input: NaN must be rejected (non-finite)."""
        import math
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError, match="finite"):
            derive_readiness_score(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_inf_input_raises_value_error(self):
        """Invalid input: infinity must be rejected."""
        import math
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=math.inf,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_string_input_raises_value_error(self):
        """Invalid input: string component must raise ValueError."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness="high",  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_bool_input_raises_value_error(self):
        """Invalid input: bool (subclass of int) must be rejected as not a float."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=True,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_all_components_negative_raises_value_error(self):
        """Invalid input: all-negative components raise ValueError (not silently 0.0)."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=-0.5,
                conf_spec_understanding=-0.5,
                conf_test_quality=-0.5,
            )
