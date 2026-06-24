"""Tests for progress_events module - JSONL progress event stream."""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.progress_events import emit_event


class TestEmitEventFileCreation:
    def test_creates_progress_jsonl_in_bob3_dir(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(
                event_type="feature_started",
                payload={"feature_id": "abc"},
                project_id="proj-1",
                feature_id="feat-1",
                attempt_number=1,
            )
        assert jsonl_path.exists()

    def test_creates_parent_directory_if_missing(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "nested" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(
                event_type="feature_started",
                payload={},
                project_id="proj-1",
                feature_id="feat-1",
                attempt_number=1,
            )
        assert jsonl_path.parent.exists()


class TestEmitEventFormat:
    def test_writes_valid_json_object(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(
                event_type="feature_started",
                payload={"name": "my-feature"},
                project_id="proj-1",
                feature_id="feat-1",
                attempt_number=1,
            )
        lines = jsonl_path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert isinstance(record, dict)

    def test_event_contains_required_fields(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(
                event_type="feature_completed",
                payload={"result": "ok"},
                project_id="proj-42",
                feature_id="feat-99",
                attempt_number=3,
            )
        record = json.loads(jsonl_path.read_text())
        assert record["event_type"] == "feature_completed"
        assert record["project_id"] == "proj-42"
        assert record["feature_id"] == "feat-99"
        assert record["attempt_number"] == 3
        assert "timestamp" in record
        assert "payload" in record

    def test_payload_is_embedded(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        payload = {"check": "no_stubs", "passed": True, "details": "all good"}
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(
                event_type="verification_check_finished",
                payload=payload,
                project_id="p",
                feature_id="f",
                attempt_number=1,
            )
        record = json.loads(jsonl_path.read_text())
        assert record["payload"] == payload

    def test_timestamp_is_iso8601_utc(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(
                event_type="error",
                payload={"msg": "boom"},
                project_id="p",
                feature_id="f",
                attempt_number=1,
            )
        record = json.loads(jsonl_path.read_text())
        ts = record["timestamp"]
        # Must parse as ISO datetime and end with Z or +00:00
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None


class TestEmitEventAppends:
    def test_multiple_events_are_separate_lines(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event("feature_started", {}, "p", "f", 1)
            emit_event("feature_completed", {"status": "done"}, "p", "f", 1)
            emit_event("cost_checkpoint", {"cost_usd": 0.5}, "p", "f", 1)
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        for line in lines:
            record = json.loads(line)
            assert "event_type" in record

    def test_appends_not_overwrites(self, tmp_path):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event("feature_started", {"a": 1}, "p", "f", 1)
            emit_event("verification_started", {"b": 2}, "p", "f", 1)
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["event_type"] == "feature_started"


class TestEmitEventTypes:
    @pytest.mark.parametrize("event_type", [
        "feature_started",
        "feature_completed",
        "verification_started",
        "verification_check_finished",
        "evaluator_verdict",
        "security_finding",
        "cost_checkpoint",
        "error",
    ])
    def test_all_defined_event_types_accepted(self, tmp_path, event_type):
        jsonl_path = tmp_path / ".bob3" / "progress.jsonl"
        with patch("bob3.progress_events.get_progress_path", return_value=jsonl_path):
            emit_event(event_type, {}, "p", "f", 1)
        record = json.loads(jsonl_path.read_text().splitlines()[0])
        assert record["event_type"] == event_type
