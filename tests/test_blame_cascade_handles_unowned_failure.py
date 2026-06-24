"""Tests: handle_unowned_failure records unattributed_failure events."""

import pytest
from bob.orchestrator.blame_cascade import (
    handle_unowned_failure,
    charge_refinement,
    find_owner_feature,
)


def _make_feature(fid: str, pytest_paths: list[str]) -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs}


class TestHandleUnownedFailure:
    def test_records_unattributed_failure_event(self):
        events = []
        handle_unowned_failure(
            failing_test="tests/test_orphan.py::test_x",
            record_fn=events.append,
        )
        assert len(events) == 1

    def test_event_contains_test_path(self):
        events = []
        handle_unowned_failure(
            failing_test="tests/test_orphan.py::test_x",
            record_fn=events.append,
        )
        event = events[0]
        assert "tests/test_orphan.py::test_x" in str(event)

    def test_event_type_is_unattributed_failure(self):
        events = []
        handle_unowned_failure(
            failing_test="tests/test_orphan.py::test_x",
            record_fn=events.append,
        )
        event = events[0]
        # Event must be a dict or have a type/kind field indicating unattributed_failure
        if isinstance(event, dict):
            event_type = event.get("type") or event.get("event_type") or event.get("kind", "")
            assert "unattributed" in event_type.lower() or "failure" in event_type.lower()
        else:
            assert "unattributed" in str(event).lower() or "orphan" in str(event).lower()

    def test_multiple_unowned_failures_each_recorded(self):
        events = []
        handle_unowned_failure(
            failing_test="tests/test_orphan_a.py::test_x",
            record_fn=events.append,
        )
        handle_unowned_failure(
            failing_test="tests/test_orphan_b.py::test_y",
            record_fn=events.append,
        )
        assert len(events) == 2

    def test_charge_refinement_calls_handle_unowned_for_orphans(self):
        unowned_events = []
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        charge_refinement(
            failing_tests=[
                "tests/test_alpha.py::test_one",
                "tests/test_orphan.py::test_orphan",  # no owner
            ],
            all_features=features,
            increment_fn=lambda _: None,
            unowned_record_fn=unowned_events.append,
        )
        assert len(unowned_events) == 1

    def test_charge_refinement_unowned_record_fn_optional(self):
        """charge_refinement should work without unowned_record_fn."""
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        # Should not raise even if there are unowned tests and no record_fn
        result = charge_refinement(
            failing_tests=["tests/test_orphan.py::test_x"],
            all_features=features,
            increment_fn=lambda _: None,
        )
        assert result == 0  # no owned tests charged
