"""Test: self-blame guard — a feature implementing regression_attribution cannot be its own scapegoat.

Feature aaa5a7f7-74e2-4edc-b61c-ac822dfced4f

F-15f5b3b8 case: when attribution heuristic points back to the feature that
implements regression_attribution itself, mark as false_positive_self_blame and skip.
"""

from __future__ import annotations

import pytest


def _make_commit(commit_id: str, files_touched: list[str]):
    return {"commit_id": commit_id, "files_touched": files_touched}

# The feature that implements regression_attribution — F-15f5b3b8 reproduction
REGRESSION_ATTRIBUTION_FEATURE_ID = "15f5b3b8-a57f-4fb7-91e7-859767805eca"


class TestSelfBlameGuard:
    """attribute_breakage returns false_positive_self_blame when pointing to itself."""

    def test_self_blame_guard_attribute_returns_marker(self):
        from bob.orchestrator.regression_attribution import attribute_breakage
        # Set up: the regression_attribution feature owns the files that were touched
        ownership_map = {
            REGRESSION_ATTRIBUTION_FEATURE_ID: {"src/bob/orchestrator/regression_attribution.py"},
        }
        recent_commits = [
            _make_commit("c1", ["src/bob/orchestrator/regression_attribution.py"])
        ]

        result = attribute_breakage(
            failing_test_id="tests/test_regression_attribution.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        # Should mark as false_positive_self_blame and not attribute
        assert result.get("false_positive_self_blame") is True
        assert result["attributed_feature"] is None

    def test_self_blame_guard_does_not_demote_self(self):
        """demote_with_evidence skips demotion when false_positive_self_blame detected."""
        from bob.orchestrator.regression_attribution import demote_with_evidence
        demoted = []
        events = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id=REGRESSION_ATTRIBUTION_FEATURE_ID,
            evidence=["file touched"],
            confidence=0.90,
            failing_test_id="tests/test_regression_attribution.py::test_self",
            recent_commits=[_make_commit("c1", ["src/bob/orchestrator/regression_attribution.py"])],
            false_positive_self_blame=True,  # explicit guard flag
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        # Must not demote
        assert not any(s == "regression" for _, s in demoted)

    def test_self_blame_guard_emits_false_positive_event(self):
        """When self-blame guard fires, emit a false_positive_self_blame event."""
        from bob.orchestrator.regression_attribution import demote_with_evidence
        events = []

        def update_fn(feature_id, status):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        demote_with_evidence(
            feature_id=REGRESSION_ATTRIBUTION_FEATURE_ID,
            evidence=["file touched"],
            confidence=0.90,
            failing_test_id="tests/test_regression_attribution.py::test_self",
            recent_commits=[_make_commit("c1", ["src/bob/orchestrator/regression_attribution.py"])],
            false_positive_self_blame=True,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        event_types = [e["type"] for e in events]
        assert "false_positive_self_blame" in event_types

    def test_non_self_blame_feature_is_demoted_normally(self):
        """Non-self-blame features with high confidence ARE demoted."""
        from bob.orchestrator.regression_attribution import demote_with_evidence
        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id="feat-other",
            evidence=["file src/other.py touched"],
            confidence=0.80,
            failing_test_id="tests/test_other.py::test_one",
            recent_commits=[_make_commit("c1", ["src/other.py"])],
            false_positive_self_blame=False,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert any(f == "feat-other" and s == "regression" for f, s in demoted)

    def test_attribute_breakage_detects_self_blame_via_file_path(self):
        """attribute_breakage auto-detects self-blame when regression_attribution.py is in owned files."""
        from bob.orchestrator.regression_attribution import attribute_breakage

        # Any feature owning regression_attribution.py itself triggers the guard
        ownership_map = {
            "some-feature": {"src/bob/orchestrator/regression_attribution.py", "src/other.py"},
        }
        recent_commits = [
            _make_commit("c1", ["src/bob/orchestrator/regression_attribution.py"])
        ]

        result = attribute_breakage(
            failing_test_id="tests/test_something.py::test_x",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        assert result.get("false_positive_self_blame") is True
        assert result["attributed_feature"] is None
