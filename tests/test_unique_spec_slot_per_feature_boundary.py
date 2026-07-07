"""Boundary tests — empty/zero/minimum input returns a well-defined result.

Feature 24c307e5-e761-43e0-b44d-85dd268ab520.
"""

from __future__ import annotations

from bob.scheduler import compute_runnable
from bob.extract import assign_unique_spec_slot


def test_compute_runnable_empty_list():
    assert compute_runnable([]) == []


def test_assign_unique_spec_slot_empty_list():
    assert assign_unique_spec_slot([]) == []


def test_compute_runnable_single_ready_feature():
    features = [{"id": "only", "spec_slot": "F-R7-001", "status": "ready"}]
    runnable = compute_runnable(features)
    assert [f["id"] for f in runnable] == ["only"]


def test_assign_unique_spec_slot_single_feature():
    out = assign_unique_spec_slot([{"id": "only", "spec_slot": "F-R7-001"}])
    assert out[0]["spec_slot"] == "F-R7-001"


def test_compute_runnable_all_completed_returns_empty():
    features = [
        {"id": "a", "spec_slot": "F-R7-001", "status": "completed"},
        {"id": "b", "spec_slot": "F-R7-002", "status": "completed"},
    ]
    assert compute_runnable(features) == []


def test_assign_unique_spec_slot_feature_without_slot_gets_one():
    out = assign_unique_spec_slot([{"id": "only"}])
    assert out[0].get("spec_slot")
