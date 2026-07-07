"""Tests for bob.spec_slot public API.

Feature 2f4afd2a: unique spec_slot per feature; scheduler keys runnable/claim
on the feature's unique id, never on spec_slot. A completed sibling sharing a
spec_slot must never suppress a distinct pending feature.
"""

from __future__ import annotations

import pytest

from bob.spec_slot import assign_unique_spec_slot, is_runnable


# --- assign_unique_spec_slot ------------------------------------------------


def test_assign_unique_spec_slot_disambiguates_collisions():
    features = [
        {"id": "a", "spec_slot": "F-R7-003"},
        {"id": "b", "spec_slot": "F-R7-003"},
        {"id": "c", "spec_slot": "F-R7-003"},
    ]
    out = assign_unique_spec_slot(features)
    slots = [f["spec_slot"] for f in out]
    assert len(set(slots)) == 3, f"expected unique slots, got {slots}"
    assert slots[0] == "F-R7-003"


def test_assign_unique_spec_slot_preserves_other_fields():
    out = assign_unique_spec_slot([{"id": "a", "spec_slot": "S", "title": "T"}])
    assert out[0]["id"] == "a"
    assert out[0]["title"] == "T"


def test_assign_unique_spec_slot_does_not_mutate_input():
    features = [{"id": "a", "spec_slot": "S"}, {"id": "b", "spec_slot": "S"}]
    assign_unique_spec_slot(features)
    assert features[1]["spec_slot"] == "S"  # original untouched


def test_assign_unique_spec_slot_empty_list():
    assert assign_unique_spec_slot([]) == []


# --- is_runnable ------------------------------------------------------------


def test_is_runnable_ready_no_deps():
    feat = {"id": "x", "status": "ready"}
    assert is_runnable(feat, set()) is True


def test_is_runnable_pending_with_completed_deps():
    feat = {"id": "x", "status": "pending", "depends_on": ["dep1"]}
    assert is_runnable(feat, {"dep1"}) is True


def test_is_runnable_blocked_on_incomplete_dep():
    feat = {"id": "x", "status": "ready", "depends_on": ["dep1"]}
    assert is_runnable(feat, set()) is False


def test_is_runnable_completed_feature_not_runnable():
    feat = {"id": "x", "status": "completed"}
    assert is_runnable(feat, set()) is False


def test_is_runnable_keys_on_id_not_spec_slot():
    """A completed sibling sharing a spec_slot must not suppress this feature."""
    # 'sibling' completed under the same spec_slot; this feature's id is distinct
    # and NOT in completed_ids, so it stays runnable.
    feat = {"id": "audit", "spec_slot": "F-R7-003", "status": "ready"}
    completed_ids = {"sibling"}  # sibling shares spec_slot F-R7-003 but different id
    assert is_runnable(feat, completed_ids) is True


def test_is_runnable_rejects_feature_without_id():
    with pytest.raises(ValueError):
        is_runnable({"status": "ready"}, set())
