"""Error-path tests — invalid input raises ValueError, no silent success.

Feature 24c307e5-e761-43e0-b44d-85dd268ab520.
"""

from __future__ import annotations

import pytest

from bob.scheduler import compute_runnable
from bob.extract import assign_unique_spec_slot


def test_compute_runnable_rejects_non_list():
    with pytest.raises(ValueError):
        compute_runnable("not a list")


def test_compute_runnable_rejects_feature_without_id():
    with pytest.raises(ValueError):
        compute_runnable([{"spec_slot": "F-R7-001", "status": "ready"}])


def test_assign_unique_spec_slot_rejects_non_list():
    with pytest.raises(ValueError):
        assign_unique_spec_slot(42)


def test_assign_unique_spec_slot_rejects_feature_without_id_or_slot():
    with pytest.raises(ValueError):
        assign_unique_spec_slot([{"title": "no identity"}])


def test_compute_runnable_rejects_none():
    with pytest.raises(ValueError):
        compute_runnable(None)
