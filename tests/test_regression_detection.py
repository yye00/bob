"""Tests for bob.regression_detection — ownership-evidenced regression detection.

Feature dc8d200e-a2aa-4bfc-adf0-a224513d52f5

Verifies:
- has_causal_link returns True only when owned/transitive files overlap breaking files
- detect_regression_with_evidence only demotes features with causal evidence
- Unmapped tests produce regression_unattributed events, never scapegoating
- Integration via bob.orchestrator import path works
"""

from __future__ import annotations

import pytest

from bob.regression_detection import (
    check_causal_link,
    detect_regression_with_evidence,
    has_causal_evidence,
    has_causal_link,
    is_regression_ownership_evidenced,
    requires_causal_evidence,
    validate_feature_involvement,
    validate_regression_ownership,
)


# ---------------------------------------------------------------------------
# has_causal_link
# ---------------------------------------------------------------------------

class TestHasCausalLink:
    def test_direct_overlap_returns_true(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py", "src/bar.py"},
            breaking_files={"src/foo.py"},
        )
        assert result is True

    def test_no_overlap_returns_false(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/other.py"},
        )
        assert result is False

    def test_empty_owned_files_returns_false(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files={"src/foo.py"},
        )
        assert result is False

    def test_empty_breaking_files_returns_false(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files=set(),
        )
        assert result is False

    def test_transitive_dep_causes_true(self):
        # foo.py imports bar.py; bar.py was touched → causal link via transitive
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps={"src/foo.py": {"src/bar.py"}},
        )
        assert result is True

    def test_transitive_dep_not_in_breaking_files_returns_false(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/unrelated.py"},
            transitive_deps={"src/foo.py": {"src/bar.py"}},
        )
        assert result is False

    def test_both_empty_returns_false(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files=set(),
        )
        assert result is False

    def test_multiple_owned_files_any_overlap_returns_true(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/a.py", "src/b.py", "src/c.py"},
            breaking_files={"src/c.py", "src/z.py"},
        )
        assert result is True

    def test_transitive_depth_respected(self):
        # foo → bar → baz; breaking=baz; depth=1 should NOT find baz (needs depth≥2)
        result_shallow = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/baz.py"},
            transitive_deps={
                "src/foo.py": {"src/bar.py"},
                "src/bar.py": {"src/baz.py"},
            },
            max_transitive_depth=1,
        )
        # depth=1 only goes one hop from foo → bar, baz not reached
        assert result_shallow is False

        result_deep = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/baz.py"},
            transitive_deps={
                "src/foo.py": {"src/bar.py"},
                "src/bar.py": {"src/baz.py"},
            },
            max_transitive_depth=2,
        )
        assert result_deep is True

    def test_none_transitive_deps_only_checks_direct(self):
        result = has_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps=None,
        )
        assert result is False


# ---------------------------------------------------------------------------
# detect_regression_with_evidence
# ---------------------------------------------------------------------------

def _make_callbacks():
    """Return tracking update/emit/create callbacks for test assertions."""
    updates = []
    events = []
    reg_events = []
    counter = [0]

    def update_fn(fid, status):
        updates.append((fid, status))

    def emit_fn(event_type, **kwargs):
        events.append({"type": event_type, **kwargs})

    def create_fn(**kwargs):
        from bob.models import RegressionEvent
        import uuid
        counter[0] += 1
        return RegressionEvent(
            id=str(uuid.uuid4()),
            project_id=kwargs.get("project_id", "proj-1"),
            affected_feature_id=kwargs.get("affected_feature_id", ""),
            causing_feature_id=kwargs.get("causing_feature_id", ""),
            affected_tests=kwargs.get("affected_tests"),
            evidence_artifacts=kwargs.get("evidence_artifacts"),
        )

    return updates, events, create_fn, update_fn, emit_fn


class TestDetectRegressionWithEvidence:
    def test_no_newly_failing_returns_none(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True, "test_b": True},
            after_results={"test_a": True, "test_b": True},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/a.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/x.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is None
        assert updates == []
        assert events == []

    def test_causal_link_established_demotes_owner(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True},
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner_file.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owner_file.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is not None
        assert ("feat-owner", "regression") in updates

    def test_no_causal_link_does_not_demote(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True},
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner_file.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/completely_unrelated.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        # No demotion — no causal link
        assert result is None
        assert updates == []
        # An unattributed event IS filed
        assert any(e["type"] == "regression_unattributed" for e in events)

    def test_unmapped_test_files_regression_unattributed_not_scapegoated(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_unmapped": True},
            after_results={"test_unmapped": False},
            test_to_feature_map={},  # no mapping
            ownership_map={},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/foo.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is None
        assert updates == []
        assert any(e["type"] == "regression_unattributed" for e in events)
        unattr = [e for e in events if e["type"] == "regression_unattributed"]
        assert unattr[0]["feature_id"] is None

    def test_already_failing_test_not_counted_as_regression(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": False},  # already failing
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owner.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is None
        assert updates == []

    def test_mixed_mapped_and_unmapped_tests(self):
        """Mapped test with causal link → demotion; unmapped → unattributed."""
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_mapped": True, "test_orphan": True},
            after_results={"test_mapped": False, "test_orphan": False},
            test_to_feature_map={"test_mapped": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owner.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is not None
        assert ("feat-owner", "regression") in updates
        assert any(e["type"] == "regression_unattributed" for e in events)

    def test_transitive_dep_enables_demotion(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True},
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/foo.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/bar.py"]}],
            transitive_deps={"src/foo.py": {"src/bar.py"}},
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is not None
        assert ("feat-owner", "regression") in updates

    def test_test_absent_from_after_results_ignored(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True},
            after_results={},  # test_a disappeared
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owner.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is None
        assert updates == []

    def test_multiple_commits_union_of_touched_files(self):
        """Breaking files are the union across all recent_commits."""
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True},
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/second_commit_file.py"}},
            recent_commits=[
                {"commit_id": "abc", "files_touched": ["src/first.py"]},
                {"commit_id": "def", "files_touched": ["src/second_commit_file.py"]},
            ],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is not None
        assert ("feat-owner", "regression") in updates

    def test_empty_before_results_no_regression(self):
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={},
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owner.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is None
        assert updates == []

    def test_evidence_stored_in_regression_event(self):
        import json
        updates, events, create_fn, update_fn, emit_fn = _make_callbacks()
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="feat-cause",
            before_results={"test_a": True},
            after_results={"test_a": False},
            test_to_feature_map={"test_a": "feat-owner"},
            ownership_map={"feat-owner": {"src/owner.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owner.py"]}],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
            _create_regression_event_fn=create_fn,
        )
        assert result is not None
        assert result.evidence_artifacts is not None
        evidence = json.loads(result.evidence_artifacts)
        assert isinstance(evidence, list)
        assert len(evidence) > 0


# ---------------------------------------------------------------------------
# Integration: importable from bob.orchestrator
# ---------------------------------------------------------------------------

class TestHasCausalEvidence:
    """has_causal_evidence is an alias for has_causal_link — verify same behaviour."""

    def test_is_same_callable_as_has_causal_link(self):
        assert has_causal_evidence is has_causal_link

    def test_direct_overlap_returns_true(self):
        result = has_causal_evidence(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )
        assert result is True

    def test_no_overlap_returns_false(self):
        result = has_causal_evidence(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
        )
        assert result is False


class TestOrchestratorIntegration:
    def test_detect_regression_with_evidence_importable_from_orchestrator(self):
        from bob.orchestrator import detect_regression_with_evidence as fn
        assert callable(fn)

    def test_has_causal_link_importable_from_orchestrator(self):
        from bob.orchestrator import has_causal_link as fn
        assert callable(fn)

    def test_has_causal_evidence_importable_from_orchestrator(self):
        from bob.orchestrator import has_causal_evidence as fn
        assert callable(fn)

    def test_has_causal_evidence_same_as_has_causal_link_via_orchestrator(self):
        from bob.orchestrator import has_causal_evidence, has_causal_link
        assert has_causal_evidence is has_causal_link


# ---------------------------------------------------------------------------
# validate_regression_ownership
# ---------------------------------------------------------------------------

class TestValidateRegressionOwnership:
    def test_direct_overlap_returns_true_with_evidence(self):
        has_ev, evidence = validate_regression_ownership(
            feature_id="feat-1",
            owned_files={"src/foo.py", "src/bar.py"},
            breaking_files={"src/foo.py", "src/other.py"},
        )
        assert has_ev is True
        assert isinstance(evidence, list)
        assert len(evidence) > 0
        assert any("src/foo.py" in e for e in evidence)

    def test_no_overlap_returns_false_empty_evidence(self):
        has_ev, evidence = validate_regression_ownership(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/unrelated.py"},
        )
        assert has_ev is False
        assert evidence == []

    def test_empty_owned_files_returns_false(self):
        has_ev, evidence = validate_regression_ownership(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files={"src/foo.py"},
        )
        assert has_ev is False
        assert evidence == []

    def test_empty_breaking_files_returns_false(self):
        has_ev, evidence = validate_regression_ownership(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files=set(),
        )
        assert has_ev is False
        assert evidence == []

    def test_transitive_dep_returns_true_with_evidence(self):
        has_ev, evidence = validate_regression_ownership(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps={"src/foo.py": {"src/bar.py"}},
        )
        assert has_ev is True
        assert any("src/bar.py" in e for e in evidence)

    def test_invalid_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_id"):
            validate_regression_ownership(
                feature_id="",
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_none_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_id"):
            validate_regression_ownership(
                feature_id=None,
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_invalid_owned_files_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="owned_files"):
            validate_regression_ownership(
                feature_id="feat-1",
                owned_files=["src/foo.py"],
                breaking_files={"src/foo.py"},
            )

    def test_invalid_breaking_files_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="breaking_files"):
            validate_regression_ownership(
                feature_id="feat-1",
                owned_files={"src/foo.py"},
                breaking_files=["src/foo.py"],
            )

    def test_db_detect_regression_importable(self):
        from bob.db.detect_regression import detect_regression
        assert callable(detect_regression)

    def test_validate_regression_ownership_importable(self):
        from bob.regression_detection import validate_regression_ownership
        assert callable(validate_regression_ownership)


# ---------------------------------------------------------------------------
# validate_feature_involvement
# ---------------------------------------------------------------------------

class TestValidateFeatureInvolvement:
    def test_direct_overlap_returns_true_with_evidence(self):
        involved, evidence = validate_feature_involvement(
            feature_id="feat-1",
            owned_files={"src/foo.py", "src/bar.py"},
            breaking_files={"src/foo.py"},
        )
        assert involved is True
        assert len(evidence) >= 1
        assert any("src/foo.py" in e for e in evidence)

    def test_no_overlap_returns_false_empty_evidence(self):
        involved, evidence = validate_feature_involvement(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/unrelated.py"},
        )
        assert involved is False
        assert evidence == []

    def test_empty_owned_files_returns_false(self):
        involved, evidence = validate_feature_involvement(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files={"src/foo.py"},
        )
        assert involved is False
        assert evidence == []

    def test_empty_breaking_files_returns_false(self):
        involved, evidence = validate_feature_involvement(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files=set(),
        )
        assert involved is False
        assert evidence == []

    def test_transitive_dep_establishes_involvement(self):
        involved, evidence = validate_feature_involvement(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps={"src/foo.py": {"src/bar.py"}},
        )
        assert involved is True
        assert any("src/bar.py" in e for e in evidence)

    def test_empty_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_id"):
            validate_feature_involvement(
                feature_id="",
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_none_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            validate_feature_involvement(
                feature_id=None,
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_list_owned_files_raises_valueerror(self):
        with pytest.raises(ValueError, match="owned_files"):
            validate_feature_involvement(
                feature_id="feat-1",
                owned_files=["src/foo.py"],
                breaking_files={"src/foo.py"},
            )

    def test_list_breaking_files_raises_valueerror(self):
        with pytest.raises(ValueError, match="breaking_files"):
            validate_feature_involvement(
                feature_id="feat-1",
                owned_files={"src/foo.py"},
                breaking_files=["src/foo.py"],
            )

    def test_importable_from_regression_detection(self):
        from bob.regression_detection import validate_feature_involvement
        assert callable(validate_feature_involvement)


# ---------------------------------------------------------------------------
# is_regression_ownership_evidenced  (AC: bob.regression_detection)
# ---------------------------------------------------------------------------

class TestIsRegressionOwnershipEvidenced:
    def test_direct_overlap_returns_true(self):
        result = is_regression_ownership_evidenced(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )
        assert result is True

    def test_no_overlap_returns_false(self):
        result = is_regression_ownership_evidenced(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
        )
        assert result is False

    def test_empty_owned_files_returns_false(self):
        result = is_regression_ownership_evidenced(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files={"src/foo.py"},
        )
        assert result is False

    def test_empty_breaking_files_returns_false(self):
        result = is_regression_ownership_evidenced(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files=set(),
        )
        assert result is False

    def test_transitive_dep_causes_true(self):
        result = is_regression_ownership_evidenced(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/dep.py"},
            transitive_deps={"src/foo.py": {"src/dep.py"}},
        )
        assert result is True

    def test_invalid_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_id"):
            is_regression_ownership_evidenced(
                feature_id="",
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_list_owned_files_raises_valueerror(self):
        with pytest.raises(ValueError, match="owned_files"):
            is_regression_ownership_evidenced(
                feature_id="feat-1",
                owned_files=["src/foo.py"],
                breaking_files={"src/foo.py"},
            )

    def test_returns_bool(self):
        result = is_regression_ownership_evidenced(
            feature_id="feat-1",
            owned_files={"src/x.py"},
            breaking_files={"src/x.py"},
        )
        assert isinstance(result, bool)

    def test_importable_from_regression_detection(self):
        from bob.regression_detection import is_regression_ownership_evidenced as fn
        assert callable(fn)


# ---------------------------------------------------------------------------
# check_causal_link  (AC: bob.regression_detection)
# ---------------------------------------------------------------------------

class TestCheckCausalLink:
    def test_direct_overlap_returns_true(self):
        result = check_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )
        assert result is True

    def test_no_overlap_returns_false(self):
        result = check_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/other.py"},
        )
        assert result is False

    def test_empty_owned_files_returns_false(self):
        result = check_causal_link(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files={"src/foo.py"},
        )
        assert result is False

    def test_empty_breaking_files_returns_false(self):
        result = check_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files=set(),
        )
        assert result is False

    def test_transitive_dep_returns_true(self):
        result = check_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/dep.py"},
            transitive_deps={"src/foo.py": {"src/dep.py"}},
        )
        assert result is True

    def test_none_transitive_deps_does_not_raise(self):
        result = check_causal_link(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps=None,
        )
        assert result is False

    def test_consistent_with_has_causal_link(self):
        kwargs = dict(
            feature_id="feat-1",
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )
        assert check_causal_link(**kwargs) == has_causal_link(**kwargs)

    def test_importable_from_regression_detection(self):
        from bob.regression_detection import check_causal_link as fn
        assert callable(fn)
