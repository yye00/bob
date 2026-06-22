"""Tests for bob3.regression.ownership_detector.

Feature a166a32e-d5b9-436a-938e-243319f03245: Ownership-evidenced regression
detection — no scapegoat without proof.

Covers:
- has_ownership_evidence: direct overlap, transitive overlap, no overlap
- detect_regression_with_evidence: demotion only with causal link,
  unattributed events for orphan/unlinked tests
- integration: bob3.detect_regression re-exports
"""

from __future__ import annotations

import pytest

from bob3.regression.ownership_detector import (
    has_ownership_evidence,
    detect_regression_with_evidence,
)


# ---------------------------------------------------------------------------
# has_ownership_evidence
# ---------------------------------------------------------------------------

class TestHasOwnershipEvidence:
    """Tests for has_ownership_evidence."""

    def test_direct_overlap_returns_true_with_evidence(self):
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py", "src/b.py"},
            breaking_files={"src/b.py", "src/c.py"},
        )
        assert ev is True
        assert len(evlist) >= 1
        assert any("src/b.py" in e for e in evlist)

    def test_no_overlap_returns_false_empty_evidence(self):
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py"},
            breaking_files={"src/z.py"},
        )
        assert ev is False
        assert evlist == []

    def test_transitive_overlap_returns_true(self):
        """A transitive dependency in the breaking diff triggers evidence."""
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py"},
            breaking_files={"src/c.py"},
            transitive_deps={"src/a.py": {"src/b.py"}, "src/b.py": {"src/c.py"}},
            max_transitive_depth=2,
        )
        assert ev is True
        assert len(evlist) >= 1

    def test_transitive_no_overlap_returns_false(self):
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py"},
            breaking_files={"src/z.py"},
            transitive_deps={"src/a.py": {"src/b.py"}},
        )
        assert ev is False
        assert evlist == []

    def test_empty_owned_files_returns_false(self):
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files={"src/a.py"},
        )
        assert ev is False
        assert evlist == []

    def test_empty_breaking_files_returns_false(self):
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py"},
            breaking_files=set(),
        )
        assert ev is False
        assert evlist == []

    def test_both_empty_returns_false(self):
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files=set(),
            breaking_files=set(),
        )
        assert ev is False
        assert evlist == []

    def test_frozenset_owned_files_accepted(self):
        ev, _ = has_ownership_evidence(
            feature_id="feat-1",
            owned_files=frozenset({"src/a.py"}),
            breaking_files={"src/a.py"},
        )
        assert ev is True

    def test_frozenset_breaking_files_accepted(self):
        ev, _ = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py"},
            breaking_files=frozenset({"src/a.py"}),
        )
        assert ev is True

    def test_transitive_depth_zero_no_transitive(self):
        """max_transitive_depth=0 means no transitive lookup."""
        ev, evlist = has_ownership_evidence(
            feature_id="feat-1",
            owned_files={"src/a.py"},
            breaking_files={"src/b.py"},
            transitive_deps={"src/a.py": {"src/b.py"}},
            max_transitive_depth=0,
        )
        assert ev is False
        assert evlist == []

    def test_invalid_feature_id_empty_raises(self):
        with pytest.raises(ValueError, match="feature_id"):
            has_ownership_evidence(
                feature_id="",
                owned_files={"src/a.py"},
                breaking_files={"src/a.py"},
            )

    def test_invalid_feature_id_whitespace_raises(self):
        with pytest.raises(ValueError, match="feature_id"):
            has_ownership_evidence(
                feature_id="   ",
                owned_files={"src/a.py"},
                breaking_files={"src/a.py"},
            )

    def test_invalid_owned_files_list_raises(self):
        with pytest.raises(ValueError, match="owned_files"):
            has_ownership_evidence(
                feature_id="feat-1",
                owned_files=["src/a.py"],
                breaking_files={"src/a.py"},
            )

    def test_invalid_breaking_files_list_raises(self):
        with pytest.raises(ValueError, match="breaking_files"):
            has_ownership_evidence(
                feature_id="feat-1",
                owned_files={"src/a.py"},
                breaking_files=["src/a.py"],
            )


# ---------------------------------------------------------------------------
# detect_regression_with_evidence
# ---------------------------------------------------------------------------

class TestDetectRegressionWithEvidence:
    """Tests for detect_regression_with_evidence."""

    def _make_args(self, **overrides):
        defaults = dict(
            project_id="proj-1",
            causing_feature_id="cause-feat",
            before_results={"tests/test_a.py::test_one": True},
            after_results={"tests/test_a.py::test_one": False},
            test_to_feature_map={"tests/test_a.py::test_one": "feat-owned"},
            ownership_map={"feat-owned": {"src/owned.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owned.py"]}],
        )
        defaults.update(overrides)
        return defaults

    def test_causal_link_confirmed_calls_update_and_creates_event(self):
        updated = {}
        events = []

        def mock_update(fid, status):
            updated[fid] = status

        def mock_create(**kwargs):
            events.append(kwargs)
            return kwargs

        result = detect_regression_with_evidence(
            **self._make_args(),
            _update_feature_fn=mock_update,
            _emit_event_fn=lambda et, **kw: None,
            _create_regression_event_fn=mock_create,
        )
        assert updated == {"feat-owned": "regression"}
        assert len(events) == 1
        assert result is not None

    def test_no_causal_link_emits_unattributed_no_demotion(self):
        updated = {}
        emitted = []

        def mock_update(fid, status):
            updated[fid] = status

        def mock_emit(event_type, **kw):
            emitted.append((event_type, kw))

        detect_regression_with_evidence(
            **self._make_args(
                ownership_map={"feat-owned": {"src/unrelated.py"}},
            ),
            _update_feature_fn=mock_update,
            _emit_event_fn=mock_emit,
            _create_regression_event_fn=lambda **kw: kw,
        )
        assert not updated
        assert any(et == "regression_unattributed" for et, _ in emitted)

    def test_unmapped_test_emits_unattributed_no_demotion(self):
        updated = {}
        emitted = []

        detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="cause-feat",
            before_results={"tests/orphan.py::test_x": True},
            after_results={"tests/orphan.py::test_x": False},
            test_to_feature_map={},  # no mapping
            ownership_map={},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/a.py"]}],
            _update_feature_fn=lambda fid, status: updated.update({fid: status}),
            _emit_event_fn=lambda et, **kw: emitted.append((et, kw)),
            _create_regression_event_fn=lambda **kw: kw,
        )
        assert not updated
        assert any(et == "regression_unattributed" for et, _ in emitted)

    def test_no_newly_failing_tests_returns_none(self):
        result = detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="cause-feat",
            before_results={"tests/test_a.py::test_one": True},
            after_results={"tests/test_a.py::test_one": True},  # still passing
            test_to_feature_map={"tests/test_a.py::test_one": "feat-owned"},
            ownership_map={"feat-owned": {"src/owned.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/owned.py"]}],
            _update_feature_fn=lambda fid, status: None,
            _emit_event_fn=lambda et, **kw: None,
            _create_regression_event_fn=lambda **kw: kw,
        )
        assert result is None

    def test_empty_recent_commits_no_evidence_no_demotion(self):
        updated = {}
        emitted = []

        detect_regression_with_evidence(
            **self._make_args(recent_commits=[]),
            _update_feature_fn=lambda fid, status: updated.update({fid: status}),
            _emit_event_fn=lambda et, **kw: emitted.append((et, kw)),
            _create_regression_event_fn=lambda **kw: kw,
        )
        # No breaking files → no causal link → unattributed
        assert not updated
        assert any(et == "regression_unattributed" for et, _ in emitted)

    def test_invalid_project_id_raises(self):
        with pytest.raises(ValueError, match="project_id"):
            detect_regression_with_evidence(
                **self._make_args(project_id=""),
            )

    def test_invalid_causing_feature_id_raises(self):
        with pytest.raises(ValueError, match="causing_feature_id"):
            detect_regression_with_evidence(
                **self._make_args(causing_feature_id=""),
            )

    def test_invalid_before_results_raises(self):
        with pytest.raises(ValueError, match="before_results"):
            detect_regression_with_evidence(
                **self._make_args(before_results=None),
            )

    def test_invalid_recent_commits_raises(self):
        with pytest.raises(ValueError, match="recent_commits"):
            detect_regression_with_evidence(
                **self._make_args(recent_commits=None),
            )

    def test_transitive_causal_link_demotes(self):
        """Transitive dep in breaking files triggers demotion."""
        updated = {}

        detect_regression_with_evidence(
            project_id="proj-1",
            causing_feature_id="cause-feat",
            before_results={"tests/test_a.py::test_one": True},
            after_results={"tests/test_a.py::test_one": False},
            test_to_feature_map={"tests/test_a.py::test_one": "feat-a"},
            ownership_map={"feat-a": {"src/a.py"}},
            recent_commits=[{"commit_id": "abc", "files_touched": ["src/c.py"]}],
            transitive_deps={"src/a.py": {"src/b.py"}, "src/b.py": {"src/c.py"}},
            _update_feature_fn=lambda fid, status: updated.update({fid: status}),
            _emit_event_fn=lambda et, **kw: None,
            _create_regression_event_fn=lambda **kw: kw,
        )
        assert updated == {"feat-a": "regression"}


# ---------------------------------------------------------------------------
# Integration: bob3.detect_regression re-exports
# ---------------------------------------------------------------------------

class TestIntegrationDetectRegression:
    """Verify the integration AC: bob3.detect_regression is wired."""

    def test_detect_regression_importable_from_bob3(self):
        """bob3.detect_regression module must be importable."""
        import bob3.detect_regression  # noqa: F401

    def test_detect_regression_with_evidence_importable_from_regression_package(self):
        """bob3.regression.ownership_detector must export detect_regression_with_evidence."""
        from bob3.regression.ownership_detector import detect_regression_with_evidence
        assert callable(detect_regression_with_evidence)

    def test_has_ownership_evidence_importable_from_regression_package(self):
        """bob3.regression.ownership_detector must export has_ownership_evidence."""
        from bob3.regression.ownership_detector import has_ownership_evidence
        assert callable(has_ownership_evidence)

    def test_regression_package_re_exports_both_functions(self):
        """bob3.regression package must re-export both functions."""
        import bob3.regression as reg
        assert hasattr(reg, "has_ownership_evidence")
        assert hasattr(reg, "detect_regression_with_evidence")
