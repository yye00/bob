"""Test: regression attribution rejects scapegoating features without file-level evidence.

Feature aaa5a7f7-74e2-4edc-b61c-ac822dfced4f
"""

from __future__ import annotations

import pytest


def _make_commit(commit_id: str, files_touched: list[str]):
    return {"commit_id": commit_id, "files_touched": files_touched}


class TestRejectsScapegoatWithoutEvidence:
    """demote_with_evidence must not transition to regression without evidence."""

    def test_demote_with_evidence_importable(self):
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        assert callable(demote_with_evidence)

    def test_empty_evidence_does_not_demote(self):
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        demoted = []
        unattributed_events = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            unattributed_events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id="feat-A",
            evidence=[],  # no evidence
            confidence=0.0,
            failing_test_id="tests/test_a.py::test_one",
            recent_commits=[_make_commit("c1", ["src/bar.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        # Must not demote
        assert not any(s == "regression" for _, s in demoted)

    def test_low_confidence_does_not_demote(self):
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        demoted = []
        events = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id="feat-A",
            evidence=["file src/foo.py touched by commit c1"],
            confidence=0.59,  # below 0.60 threshold
            failing_test_id="tests/test_a.py::test_one",
            recent_commits=[_make_commit("c1", ["src/foo.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        # Must not demote — confidence below threshold
        assert not any(s == "regression" for _, s in demoted)

    def test_evidence_above_threshold_demotes(self):
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        demoted = []
        events = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id="feat-A",
            evidence=["file src/foo.py touched by commit c1"],
            confidence=0.80,
            failing_test_id="tests/test_a.py::test_one",
            recent_commits=[_make_commit("c1", ["src/foo.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        # Should demote
        assert any(f == "feat-A" and s == "regression" for f, s in demoted)

    def test_empty_evidence_emits_regression_unattributed(self):
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        events = []

        def update_fn(feature_id, status):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id=None,  # no attribution
            evidence=[],
            confidence=0.0,
            failing_test_id="tests/test_x.py::test_one",
            recent_commits=[_make_commit("c1", ["src/other.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        event_types = [e["type"] for e in events]
        assert "regression_unattributed" in event_types

    def test_regression_unattributed_event_contains_failing_test_and_commits(self):
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        events = []

        def update_fn(feature_id, status):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        commits = [_make_commit("c1", ["src/other.py"])]
        demote_with_evidence(
            feature_id=None,
            evidence=[],
            confidence=0.0,
            failing_test_id="tests/test_x.py::test_fail",
            recent_commits=commits,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        unattr = [e for e in events if e["type"] == "regression_unattributed"]
        assert len(unattr) == 1
        assert unattr[0]["failing_test_id"] == "tests/test_x.py::test_fail"
        assert "recent_commits" in unattr[0]

    def test_exact_threshold_60_demotes(self):
        """Confidence exactly 0.60 should demote (>= 0.60)."""
        from bob3.orchestrator.regression_attribution import demote_with_evidence
        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id="feat-B",
            evidence=["file src/b.py touched"],
            confidence=0.60,
            failing_test_id="tests/test_b.py::test_one",
            recent_commits=[_make_commit("c1", ["src/b.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert any(f == "feat-B" and s == "regression" for f, s in demoted)
