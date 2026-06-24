"""Demonstrator F-R7-482: v.12 scapegoat scenario replay.

Asserts the three core guarantees of feature aaa5a7f7:
  (a) A feature NOT touched by the breaking commit is NEVER demoted.
  (b) regression_unattributed fires when attribution fails.
  (c) Self-blame guard fires on the F-15f5b3b8 reproduction.
"""

from __future__ import annotations


def _make_commit(commit_id: str, files_touched: list[str]) -> dict:
    return {"commit_id": commit_id, "files_touched": files_touched}


class TestDemonstratorScapegoatImmunity:
    """(a) Feature NOT touched by breaking commit is NEVER demoted."""

    def test_innocent_feature_not_attributed(self):
        from bob.orchestrator.regression_attribution import attribute_breakage

        ownership_map = {
            "feat-innocent": {"src/feature_a.py"},
            "feat-cause": {"src/feature_b.py"},
        }
        recent_commits = [_make_commit("break-c1", ["src/feature_b.py"])]

        result = attribute_breakage(
            failing_test_id="tests/test_feature_b.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        assert result["attributed_feature"] != "feat-innocent", (
            "feat-innocent did not touch the breaking file and must not be attributed"
        )

    def test_cause_feature_is_attributed(self):
        from bob.orchestrator.regression_attribution import attribute_breakage

        ownership_map = {
            "feat-innocent": {"src/feature_a.py"},
            "feat-cause": {"src/feature_b.py"},
        }
        recent_commits = [_make_commit("break-c1", ["src/feature_b.py"])]

        result = attribute_breakage(
            failing_test_id="tests/test_feature_b.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        # feat-cause owns the touched file and the test name matches "feature_b"
        assert result["attributed_feature"] == "feat-cause"

    def test_demote_innocent_without_evidence_does_not_change_status(self):
        from bob.orchestrator.regression_attribution import demote_with_evidence

        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id="feat-innocent",
            evidence=[],  # no evidence
            confidence=0.0,
            failing_test_id="tests/test_something.py::test_one",
            recent_commits=[_make_commit("c1", ["src/unrelated.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert not any(s == "regression" for _, s in demoted), (
            "Feature with no evidence must not be demoted to regression"
        )


class TestDemonstratorRegressionUnattributed:
    """(b) regression_unattributed fires when attribution fails."""

    def test_unattributed_event_emitted_when_no_evidence(self):
        from bob.orchestrator.regression_attribution import demote_with_evidence

        events = []

        def update_fn(feature_id, status):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id=None,
            evidence=[],
            confidence=0.0,
            failing_test_id="tests/test_unowned.py::test_one",
            recent_commits=[_make_commit("c1", ["src/unknown_module.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        event_types = [e["type"] for e in events]
        assert "regression_unattributed" in event_types, (
            "regression_unattributed event must be emitted when attribution fails"
        )

    def test_unattributed_event_contains_failing_test_and_commits(self):
        from bob.orchestrator.regression_attribution import demote_with_evidence

        events = []
        commits = [_make_commit("c1", ["src/unknown_module.py"])]

        def update_fn(feature_id, status):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id=None,
            evidence=[],
            confidence=0.0,
            failing_test_id="tests/test_unowned.py::test_one",
            recent_commits=commits,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        unattributed = [e for e in events if e["type"] == "regression_unattributed"]
        assert len(unattributed) == 1
        event = unattributed[0]
        assert "failing_test_id" in event, "Event must contain failing_test_id"
        assert "recent_commits" in event, "Event must contain recent_commits"
        assert event["failing_test_id"] == "tests/test_unowned.py::test_one"

    def test_no_status_change_when_unattributed(self):
        from bob.orchestrator.regression_attribution import demote_with_evidence

        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id=None,
            evidence=[],
            confidence=0.0,
            failing_test_id="tests/test_unowned.py::test_one",
            recent_commits=[_make_commit("c1", ["src/unknown_module.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert not demoted, "No status change must occur when regression is unattributed"


class TestDemonstratorSelfBlameGuard:
    """(c) Self-blame guard fires on F-15f5b3b8 reproduction."""

    REGRESSION_ATTRIBUTION_FEATURE_ID = "15f5b3b8-a57f-4fb7-91e7-859767805eca"

    def test_self_blame_guard_fires_on_v12_incident_reproduction(self):
        from bob.orchestrator.regression_attribution import attribute_breakage

        # F-15f5b3b8 scenario: the ONLY feature in map owns regression_attribution.py
        # which is the only file touched in the breaking commit.
        ownership_map = {
            self.REGRESSION_ATTRIBUTION_FEATURE_ID: {
                "src/bob/orchestrator/regression_attribution.py"
            },
        }
        recent_commits = [
            _make_commit("self-break-c1", ["src/bob/orchestrator/regression_attribution.py"])
        ]

        result = attribute_breakage(
            failing_test_id="tests/test_regression_attribution.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        assert result.get("false_positive_self_blame") is True, (
            "Self-blame guard must fire when regression_attribution feature is its own scapegoat"
        )
        assert result["attributed_feature"] is None, (
            "attributed_feature must be None when self-blame guard fires"
        )

    def test_self_blame_guard_prevents_demotion(self):
        from bob.orchestrator.regression_attribution import demote_with_evidence

        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id=self.REGRESSION_ATTRIBUTION_FEATURE_ID,
            evidence=["file regression_attribution.py touched"],
            confidence=0.95,
            failing_test_id="tests/test_regression_attribution.py::test_one",
            recent_commits=[
                _make_commit("self-break-c1", ["src/bob/orchestrator/regression_attribution.py"])
            ],
            false_positive_self_blame=True,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert not any(s == "regression" for _, s in demoted), (
            "Self-blame guard must prevent demotion even with high confidence"
        )

    def test_self_blame_guard_emits_false_positive_event(self):
        from bob.orchestrator.regression_attribution import demote_with_evidence

        events = []

        def update_fn(feature_id, status):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id=self.REGRESSION_ATTRIBUTION_FEATURE_ID,
            evidence=["file touched"],
            confidence=0.95,
            failing_test_id="tests/test_regression_attribution.py::test_one",
            recent_commits=[
                _make_commit("self-break-c1", ["src/bob/orchestrator/regression_attribution.py"])
            ],
            false_positive_self_blame=True,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        event_types = [e["type"] for e in events]
        assert "false_positive_self_blame" in event_types, (
            "A false_positive_self_blame event must be emitted when guard fires"
        )
