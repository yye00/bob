"""Tests that attribute_regression_to_owner re-opens terminal-state owners.

AC-13: asserts terminal-state owner is re-opened with sentinel when its test
newly regresses (error/recovery path).
"""
from __future__ import annotations

import pytest

from bob.verification.regression_attribution import (
    attribute_regression_to_owner,
    owning_feature_for_test,
)

OWNER_FEATURE = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OWNER_TEST = f"tests/{OWNER_FEATURE}/test_ac_5.py::test_regression"
PREVIOUSLY_PASSED_AT = "2026-05-29T14:11:00Z"


class TestAttributeRegressionToOwnerTerminalState:
    """attribute_regression_to_owner re-opens features in terminal states."""

    @pytest.mark.parametrize("terminal_status", [
        "completed", "failed", "needs_human", "rolled_back", "regression"
    ])
    def test_reopens_owner_in_terminal_state(self, terminal_status):
        updates = {}
        events = []

        def update_fn(fid, **kwargs):
            updates[fid] = kwargs

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        features = [{"id": OWNER_FEATURE, "status": terminal_status}]

        result = attribute_regression_to_owner(
            OWNER_TEST,
            previously_passed_at=PREVIOUSLY_PASSED_AT,
            all_features=features,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert result == OWNER_FEATURE
        assert OWNER_FEATURE in updates, "update_feature must be called with owner_id"
        assert updates[OWNER_FEATURE]["status"] == "needs_human"
        assert updates[OWNER_FEATURE]["refinement_attempts"] == 0

    def test_sentinel_key_in_emitted_event(self):
        events = []

        def update_fn(fid, **kwargs):
            pass

        def emit_fn(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        features = [{"id": OWNER_FEATURE, "status": "completed"}]

        attribute_regression_to_owner(
            OWNER_TEST,
            previously_passed_at=PREVIOUSLY_PASSED_AT,
            all_features=features,
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert len(events) >= 1
        sentinel_event = next(
            (e for e in events if e.get("test_regression_reattributed_to") == OWNER_FEATURE),
            None,
        )
        assert sentinel_event is not None, (
            "Must emit event with sentinel key test_regression_reattributed_to=<owner_id>"
        )
        assert sentinel_event.get("test_path") == OWNER_TEST

    def test_previously_passed_at_in_event(self):
        events = []

        features = [{"id": OWNER_FEATURE, "status": "completed"}]

        attribute_regression_to_owner(
            OWNER_TEST,
            previously_passed_at=PREVIOUSLY_PASSED_AT,
            all_features=features,
            _update_feature_fn=lambda fid, **kw: None,
            _emit_event_fn=lambda et, **kw: events.append({"type": et, **kw}),
        )

        reattributed = next(
            (e for e in events if "test_regression_reattributed_to" in e), None
        )
        assert reattributed is not None
        assert reattributed.get("previously_passed_at") == PREVIOUSLY_PASSED_AT


class TestAttributeRegressionOrphanCase:
    """When no owner is found, emit orphan_test_regression and do NOT gate-block."""

    def test_orphan_test_emits_event_not_raises(self):
        events = []
        updates = {}

        result = attribute_regression_to_owner(
            "tests/test_top_level_orphan.py::test_something",
            previously_passed_at=PREVIOUSLY_PASSED_AT,
            all_features=[],
            _update_feature_fn=lambda fid, **kw: updates.update({fid: kw}),
            _emit_event_fn=lambda et, **kw: events.append({"type": et, **kw}),
        )

        assert result is None, "Orphan tests must return None"
        assert len(updates) == 0, "No feature must be updated for orphan tests"

        orphan_events = [e for e in events if e["type"] == "orphan_test_regression"]
        assert len(orphan_events) == 1
        assert orphan_events[0].get("test_path") == "tests/test_top_level_orphan.py::test_something"
        assert orphan_events[0].get("previously_passed_at") == PREVIOUSLY_PASSED_AT

    def test_no_update_called_for_orphan(self):
        updates = {}

        attribute_regression_to_owner(
            "tests/test_orphan.py",
            all_features=None,
            _update_feature_fn=lambda fid, **kw: updates.update({fid: kw}),
            _emit_event_fn=lambda et, **kw: None,
        )

        assert updates == {}, "update_feature must NOT be called for orphan tests"


class TestAttributeRegressionNonTerminalOwner:
    """When owner is NOT in a terminal state, no reopen occurs."""

    @pytest.mark.parametrize("active_status", ["pending", "ready", "in_progress"])
    def test_active_owner_not_reopened(self, active_status):
        updates = {}
        events = []

        features = [{"id": OWNER_FEATURE, "status": active_status}]

        result = attribute_regression_to_owner(
            OWNER_TEST,
            all_features=features,
            _update_feature_fn=lambda fid, **kw: updates.update({fid: kw}),
            _emit_event_fn=lambda et, **kw: events.append({"type": et, **kw}),
        )

        assert result == OWNER_FEATURE, "Owner should be identified even if not re-opened"
        assert OWNER_FEATURE not in updates, (
            "Active-state owner must NOT be re-opened"
        )
