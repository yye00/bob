"""Tests for unique spec_slot per feature — scheduler keys on feature id.

Feature 24c307e5-e761-43e0-b44d-85dd268ab520.

Acceptance criteria:
  - File exists: src/bob/scheduler.py
  - Function defined: bob.scheduler.compute_runnable
  - Function defined: bob.extract.assign_unique_spec_slot
  - pytest: tests/test_unique_spec_slot.py
  - integration: bob.superpowers

The regression this guards against: extract-from-peas emitted three feature
rows sharing spec_slot F-R7-003, and the scheduler computed runnable/claim
eligibility keyed on spec_slot. A completed sibling made the runnable-count
for the still-pending feature read 0, so the build STOPPED (QUEUE_DRAINED)
with real work left.
"""

from __future__ import annotations

import pytest

from bob.scheduler import compute_runnable
from bob.extract import assign_unique_spec_slot


# ---------------------------------------------------------------------------
# assign_unique_spec_slot
# ---------------------------------------------------------------------------

def test_assign_unique_spec_slot_disambiguates_collisions():
    features = [
        {"id": "a", "spec_slot": "F-R7-003"},
        {"id": "b", "spec_slot": "F-R7-003"},
        {"id": "c", "spec_slot": "F-R7-003"},
    ]
    out = assign_unique_spec_slot(features)
    slots = [f["spec_slot"] for f in out]
    assert len(set(slots)) == 3, f"slots must be unique, got {slots}"
    # First keeps its original slot; the rest get deterministic suffixes.
    assert slots[0] == "F-R7-003"


def test_assign_unique_spec_slot_leaves_unique_input_untouched():
    features = [
        {"id": "a", "spec_slot": "F-R7-001"},
        {"id": "b", "spec_slot": "F-R7-002"},
    ]
    out = assign_unique_spec_slot(features)
    assert [f["spec_slot"] for f in out] == ["F-R7-001", "F-R7-002"]


def test_assign_unique_spec_slot_uses_key_when_no_spec_slot():
    features = [
        {"id": "a", "key": "F-R7-003"},
        {"id": "b", "key": "F-R7-003"},
    ]
    out = assign_unique_spec_slot(features)
    slots = [f["spec_slot"] for f in out]
    assert len(set(slots)) == 2


def test_assign_unique_spec_slot_preserves_other_fields():
    features = [{"id": "a", "spec_slot": "F-R7-003", "title": "t"}]
    out = assign_unique_spec_slot(features)
    assert out[0]["title"] == "t"
    assert out[0]["id"] == "a"


# ---------------------------------------------------------------------------
# compute_runnable
# ---------------------------------------------------------------------------

def test_completed_sibling_does_not_suppress_distinct_pending_feature():
    # Two features share spec_slot; one is completed. The pending one must
    # still be runnable — eligibility is keyed on id, never spec_slot.
    features = [
        {"id": "done", "spec_slot": "F-R7-003", "status": "completed"},
        {"id": "todo", "spec_slot": "F-R7-003", "status": "ready"},
    ]
    runnable = compute_runnable(features)
    ids = {f["id"] for f in runnable}
    assert "todo" in ids
    assert "done" not in ids


def test_compute_runnable_keys_on_id_not_spec_slot():
    features = [
        {"id": "x", "spec_slot": "F-R7-003", "status": "ready"},
        {"id": "y", "spec_slot": "F-R7-003", "status": "ready"},
    ]
    runnable = compute_runnable(features)
    assert {f["id"] for f in runnable} == {"x", "y"}


def test_compute_runnable_respects_dependencies_by_id():
    features = [
        {"id": "dep", "spec_slot": "F-R7-001", "status": "ready"},
        {
            "id": "leaf",
            "spec_slot": "F-R7-002",
            "status": "ready",
            "depends_on": ["dep"],
        },
    ]
    runnable = compute_runnable(features)
    # dep is runnable; leaf is blocked until dep completes.
    assert {f["id"] for f in runnable} == {"dep"}


def test_compute_runnable_unblocks_when_dependency_completed():
    features = [
        {"id": "dep", "spec_slot": "F-R7-001", "status": "completed"},
        {
            "id": "leaf",
            "spec_slot": "F-R7-002",
            "status": "ready",
            "depends_on": ["dep"],
        },
    ]
    runnable = compute_runnable(features)
    assert {f["id"] for f in runnable} == {"leaf"}


def test_compute_runnable_excludes_executing_and_completed():
    features = [
        {"id": "a", "spec_slot": "F-R7-001", "status": "executing"},
        {"id": "b", "spec_slot": "F-R7-002", "status": "completed"},
        {"id": "c", "spec_slot": "F-R7-003", "status": "ready"},
    ]
    runnable = compute_runnable(features)
    assert {f["id"] for f in runnable} == {"c"}


def test_compute_runnable_accepts_feature_objects():
    class F:
        def __init__(self, id, status, spec_slot):
            self.id = id
            self.status = status
            self.spec_slot = spec_slot

    features = [
        F("done", "completed", "F-R7-003"),
        F("todo", "ready", "F-R7-003"),
    ]
    runnable = compute_runnable(features)
    ids = {getattr(f, "id") for f in runnable}
    assert ids == {"todo"}


# ---------------------------------------------------------------------------
# integration: bob.superpowers
# ---------------------------------------------------------------------------

def test_integration_bob_superpowers_importable():
    import bob.superpowers  # noqa: F401
