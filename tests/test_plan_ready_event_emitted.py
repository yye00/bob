"""Tests: write_plan_artifact appends PLAN_READY event to runs/events.jsonl (F-9792cc6f).

Acceptance criterion:
    pytest: tests/test_plan_ready_event_emitted.py asserts running
    plan_gate.write_plan_artifact appends "PLAN_READY" event line to runs/events.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestPlanReadyEventEmitted:
    """write_plan_artifact writes a PLAN_READY event to runs/events.jsonl."""

    def test_plan_ready_event_appended(self, tmp_path):
        from bob3.orchestrator.plan_gate import write_plan_artifact

        feature_id = "aaaa0001-plan-ready-event-test00000001"
        write_plan_artifact(
            feature_id=feature_id,
            name="Event Test Feature",
            description="Testing PLAN_READY event emission",
            acceptance_criteria=["pytest: tests/test_event.py"],
            workspace=tmp_path,
        )

        events_path = tmp_path / "runs" / "events.jsonl"
        assert events_path.exists(), "runs/events.jsonl must be created by write_plan_artifact"

        lines = events_path.read_text().strip().splitlines()
        assert len(lines) >= 1, "At least one event must be appended"

        # Find the PLAN_READY event
        plan_ready_events = []
        for line in lines:
            record = json.loads(line)
            if record.get("event") == "PLAN_READY":
                plan_ready_events.append(record)

        assert len(plan_ready_events) >= 1, (
            'runs/events.jsonl must contain a line with "PLAN_READY"'
        )
        assert plan_ready_events[0]["feature_id"] == feature_id

    def test_plan_ready_event_contains_plan_path(self, tmp_path):
        from bob3.orchestrator.plan_gate import write_plan_artifact

        feature_id = "bbbb0002-plan-ready-event-test00000002"
        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Path Test Feature",
            description=None,
            acceptance_criteria=["AC one"],
            workspace=tmp_path,
        )

        events_path = tmp_path / "runs" / "events.jsonl"
        lines = events_path.read_text().strip().splitlines()
        records = [json.loads(l) for l in lines if json.loads(l).get("event") == "PLAN_READY"]

        assert any(str(plan_path) in r.get("plan_path", "") for r in records), (
            "PLAN_READY event must include the plan_path"
        )

    def test_plan_ready_event_includes_approved_field(self, tmp_path):
        from bob3.orchestrator.plan_gate import write_plan_artifact

        feature_id = "cccc0003-plan-ready-event-test00000003"
        write_plan_artifact(
            feature_id=feature_id,
            name="Approved Field Test",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
            auto_approve=True,
        )

        events_path = tmp_path / "runs" / "events.jsonl"
        lines = events_path.read_text().strip().splitlines()
        records = [json.loads(l) for l in lines if json.loads(l).get("event") == "PLAN_READY"]

        assert len(records) >= 1
        assert records[0]["approved"] is True

    def test_multiple_writes_append_multiple_events(self, tmp_path):
        from bob3.orchestrator.plan_gate import write_plan_artifact

        fid1 = "dddd0004-plan-ready-event-test00000004"
        fid2 = "eeee0005-plan-ready-event-test00000005"

        write_plan_artifact(
            feature_id=fid1, name="F1", description=None,
            acceptance_criteria=["AC1"], workspace=tmp_path,
        )
        write_plan_artifact(
            feature_id=fid2, name="F2", description=None,
            acceptance_criteria=["AC2"], workspace=tmp_path,
        )

        events_path = tmp_path / "runs" / "events.jsonl"
        lines = events_path.read_text().strip().splitlines()
        plan_ready = [json.loads(l) for l in lines if json.loads(l).get("event") == "PLAN_READY"]

        assert len(plan_ready) == 2, "Two writes must produce two PLAN_READY events"
        feature_ids = {r["feature_id"] for r in plan_ready}
        assert fid1 in feature_ids
        assert fid2 in feature_ids

    def test_event_line_is_valid_json(self, tmp_path):
        from bob3.orchestrator.plan_gate import write_plan_artifact

        feature_id = "ffff0006-plan-ready-event-test00000006"
        write_plan_artifact(
            feature_id=feature_id,
            name="JSON Validity Test",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
        )

        events_path = tmp_path / "runs" / "events.jsonl"
        for line in events_path.read_text().strip().splitlines():
            record = json.loads(line)  # will raise if invalid JSON
            assert isinstance(record, dict)
