"""Tests for bob.decomposition — stuck-readiness decomposition trigger."""

from unittest.mock import MagicMock

import pytest

from bob.decomposition import (
    create_sub_features,
    mark_pending_decomposition,
    should_trigger_decomposition,
)
from bob.models import Feature


def make_feature(**kwargs) -> Feature:
    defaults = dict(
        id="feat-001",
        project_id="proj-001",
        name="Test Feature",
        status="ready",
        refinement_attempts=0,
        readiness_score=0.0,
        max_refinement_attempts=5,
        conf_spec_understanding=0.0,
        conf_impl_correctness=0.0,
        conf_test_adequacy=0.0,
        risk_category="medium",
        priority=100,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


# ---------------------------------------------------------------------------
# should_trigger_decomposition
# ---------------------------------------------------------------------------


class TestShouldTriggerDecomposition:
    def test_triggers_when_all_conditions_met(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert should_trigger_decomposition(f) is True

    def test_no_trigger_below_two_attempts(self):
        f = make_feature(refinement_attempts=1, readiness_score=0.3)
        assert should_trigger_decomposition(f) is False

    def test_no_trigger_when_readiness_at_threshold(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.80)
        assert should_trigger_decomposition(f) is False

    def test_no_trigger_when_readiness_above_threshold(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.90)
        assert should_trigger_decomposition(f) is False

    def test_no_trigger_when_readiness_improved(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.70)
        assert should_trigger_decomposition(f, previous_readiness_score=0.50) is False

    def test_triggers_when_readiness_did_not_improve(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.60)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is True

    def test_triggers_when_readiness_unchanged(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.60)
        assert should_trigger_decomposition(f, previous_readiness_score=0.60) is True

    def test_triggers_when_no_previous_score(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.50)
        assert should_trigger_decomposition(f, previous_readiness_score=None) is True

    def test_triggers_with_many_attempts(self):
        f = make_feature(refinement_attempts=10, readiness_score=0.30)
        assert should_trigger_decomposition(f) is True

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            should_trigger_decomposition(f)

    def test_negative_attempts_error_includes_feature_id(self):
        f = make_feature(id="corrupt-feat-abc", refinement_attempts=-3)
        with pytest.raises(ValueError, match="corrupt-feat-abc"):
            should_trigger_decomposition(f)

    def test_zero_attempts_returns_false(self):
        f = make_feature(refinement_attempts=0, readiness_score=0.0)
        assert should_trigger_decomposition(f) is False

    def test_readiness_just_below_threshold_triggers(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.799)
        assert should_trigger_decomposition(f) is True


# ---------------------------------------------------------------------------
# mark_pending_decomposition
# ---------------------------------------------------------------------------


class TestMarkPendingDecomposition:
    def test_sets_status_to_pending_decomposition(self):
        f = make_feature(refinement_attempts=2, status="ready")
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_original_feature_unchanged(self):
        f = make_feature(refinement_attempts=2, status="ready")
        mark_pending_decomposition(f)
        assert f.status == "ready"

    def test_calls_db_update_with_correct_args(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(id="feat-xyz", refinement_attempts=2)
        mark_pending_decomposition(f, db_update=fake_db_update)
        assert calls == [("feat-xyz", {"status": "pending_decomposition"})]

    def test_no_db_update_when_not_provided(self):
        f = make_feature(refinement_attempts=2)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            mark_pending_decomposition(f)

    def test_negative_attempts_does_not_call_db_update(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError):
            mark_pending_decomposition(f, db_update=fake_db_update)

        assert calls == []

    def test_negative_attempts_error_includes_feature_id(self):
        f = make_feature(id="bad-feat-99", refinement_attempts=-2)
        with pytest.raises(ValueError, match="bad-feat-99"):
            mark_pending_decomposition(f)

    def test_already_pending_decomposition_stays_pending(self):
        f = make_feature(refinement_attempts=2, status="pending_decomposition")
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"


# ---------------------------------------------------------------------------
# create_sub_features
# ---------------------------------------------------------------------------


class TestCreateSubFeatures:
    def _make_child_feature(self, parent_id: str, name: str, project_id: str) -> Feature:
        return make_feature(
            id=f"child-{name.replace(' ', '-').lower()}",
            project_id=project_id,
            name=name,
            parent_feature_id=parent_id,
            status="ready",
            refinement_attempts=0,
            readiness_score=0.0,
        )

    def test_empty_specs_raises_value_error(self):
        f = make_feature(refinement_attempts=2)
        with pytest.raises(ValueError, match="empty"):
            create_sub_features(f, [], project_id="proj-001")

    def test_non_dict_spec_raises_value_error(self):
        f = make_feature(refinement_attempts=2)
        with pytest.raises(ValueError):
            create_sub_features(f, ["not-a-dict"], project_id="proj-001")

    def test_creates_children_via_db(self, monkeypatch):
        created = []

        def fake_create_child_feature(*, parent_feature_id, project_id, name, **kwargs):
            child = make_feature(
                id=f"child-{len(created)}",
                project_id=project_id,
                name=name,
                parent_feature_id=parent_feature_id,
                status="ready",
            )
            created.append(child)
            return child

        import bob.decomposition as decomp_mod
        monkeypatch.setattr(decomp_mod, "create_sub_features", decomp_mod.create_sub_features)
        import bob.db as db_mod
        monkeypatch.setattr(db_mod, "create_child_feature", fake_create_child_feature)

        f = make_feature(id="parent-001", project_id="proj-001")
        specs = [
            {"name": "Child A", "description": "First child"},
            {"name": "Child B", "description": "Second child"},
        ]
        result = create_sub_features(f, specs, project_id="proj-001")

        assert len(result) == 2
        assert result[0].name == "Child A"
        assert result[1].name == "Child B"

    def test_default_name_when_missing(self, monkeypatch):
        created = []

        def fake_create_child_feature(*, parent_feature_id, project_id, name, **kwargs):
            child = make_feature(id=f"child-{len(created)}", project_id=project_id, name=name)
            created.append(child)
            return child

        import bob.db as db_mod
        monkeypatch.setattr(db_mod, "create_child_feature", fake_create_child_feature)

        f = make_feature(id="parent-002", name="Big Feature", project_id="proj-001")
        result = create_sub_features(f, [{}], project_id="proj-001")

        assert result[0].name == "Child of Big Feature"

    def test_inherits_parent_priority(self, monkeypatch):
        received_kwargs = {}

        def fake_create_child_feature(*, parent_feature_id, project_id, name, priority, **kwargs):
            received_kwargs["priority"] = priority
            return make_feature(id="child-0", project_id=project_id, name=name)

        import bob.db as db_mod
        monkeypatch.setattr(db_mod, "create_child_feature", fake_create_child_feature)

        f = make_feature(id="parent-003", project_id="proj-001", priority=42)
        create_sub_features(f, [{"name": "Child"}], project_id="proj-001")

        assert received_kwargs["priority"] == 42

    def test_spec_priority_overrides_parent(self, monkeypatch):
        received_kwargs = {}

        def fake_create_child_feature(*, parent_feature_id, project_id, name, priority, **kwargs):
            received_kwargs["priority"] = priority
            return make_feature(id="child-0", project_id=project_id, name=name)

        import bob.db as db_mod
        monkeypatch.setattr(db_mod, "create_child_feature", fake_create_child_feature)

        f = make_feature(id="parent-004", project_id="proj-001", priority=100)
        create_sub_features(f, [{"name": "Child", "priority": 5}], project_id="proj-001")

        assert received_kwargs["priority"] == 5
