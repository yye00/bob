"""Parity tests: both claude-progress.txt and progress.jsonl receive the same events.

Tests that update_progress_notes() writes to both:
  1. claude-progress.txt (existing text format)
  2. .bob/progress.jsonl (new structured JSONL stream via emit_event)

Both streams should carry the same core progress information for every call.
"""
import json
import pathlib
from unittest.mock import patch

import pytest

from bob.orientation import update_progress_notes, PROGRESS_FILENAME


def _call_update(workspace: pathlib.Path, jsonl_path: pathlib.Path, **kwargs) -> None:
    """Helper: call update_progress_notes with patched JSONL path."""
    defaults = dict(
        workspace=str(workspace),
        feature_id="feat-abc",
        feature_name="My Test Feature",
        outcome="completed",
        duration_ms=1234,
        num_turns=5,
        cost_usd=0.42,
        blockers=None,
        notes=None,
    )
    defaults.update(kwargs)
    with patch("bob.progress_events.get_progress_path", return_value=jsonl_path):
        update_progress_notes(**defaults)


class TestBothFilesCreated:
    def test_text_file_created(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        _call_update(tmp_path, jsonl_path)
        assert (tmp_path / PROGRESS_FILENAME).exists()

    def test_jsonl_file_created(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        _call_update(tmp_path, jsonl_path)
        assert jsonl_path.exists(), "progress.jsonl must be created on first emit"


class TestFeatureIdParity:
    def test_feature_id_in_both_streams(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        feature_id = "121fe133-01fb-44dd-93d4-77fff59b1a53"
        _call_update(tmp_path, jsonl_path, feature_id=feature_id)

        text = (tmp_path / PROGRESS_FILENAME).read_text()
        assert feature_id in text

        record = json.loads(jsonl_path.read_text().splitlines()[0])
        assert record["feature_id"] == feature_id


class TestOutcomeParity:
    @pytest.mark.parametrize("outcome", ["completed", "failed", "interrupted"])
    def test_outcome_in_both_streams(self, tmp_path, outcome):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        _call_update(tmp_path, jsonl_path, outcome=outcome)

        text = (tmp_path / PROGRESS_FILENAME).read_text()
        assert outcome in text

        record = json.loads(jsonl_path.read_text().splitlines()[0])
        payload = record["payload"]
        assert payload.get("outcome") == outcome


class TestFeatureNameParity:
    def test_feature_name_in_both_streams(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        feature_name = "Unique Feature Name XYZ"
        _call_update(tmp_path, jsonl_path, feature_name=feature_name)

        text = (tmp_path / PROGRESS_FILENAME).read_text()
        assert feature_name in text

        record = json.loads(jsonl_path.read_text().splitlines()[0])
        assert record["payload"].get("feature_name") == feature_name


class TestBlockersParity:
    def test_blockers_in_both_streams_when_set(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        blockers = "Some test blocker description"
        _call_update(tmp_path, jsonl_path, outcome="failed", blockers=blockers)

        text = (tmp_path / PROGRESS_FILENAME).read_text()
        assert blockers in text

        record = json.loads(jsonl_path.read_text().splitlines()[0])
        assert record["payload"].get("blockers") == blockers

    def test_no_blockers_key_when_none(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        _call_update(tmp_path, jsonl_path, blockers=None)

        record = json.loads(jsonl_path.read_text().splitlines()[0])
        # Either absent or None — not a non-None value
        assert record["payload"].get("blockers") is None


class TestMultipleEventsParity:
    def test_both_streams_receive_each_call(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        features = [
            ("feat-1", "Feature One", "completed"),
            ("feat-2", "Feature Two", "failed"),
            ("feat-3", "Feature Three", "completed"),
        ]
        for fid, fname, outcome in features:
            with patch("bob.progress_events.get_progress_path", return_value=jsonl_path):
                update_progress_notes(
                    workspace=str(tmp_path),
                    feature_id=fid,
                    feature_name=fname,
                    outcome=outcome,
                )

        text = (tmp_path / PROGRESS_FILENAME).read_text()
        jsonl_lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]

        assert len(jsonl_lines) == 3, f"Expected 3 JSONL events, got {len(jsonl_lines)}"

        for fid, fname, outcome in features:
            assert fid in text, f"{fid} missing from text file"
            records_with_id = [
                json.loads(l) for l in jsonl_lines
                if json.loads(l)["feature_id"] == fid
            ]
            assert records_with_id, f"No JSONL record for feature_id={fid}"
            assert records_with_id[0]["payload"]["outcome"] == outcome


class TestJsonlEventStructure:
    def test_jsonl_event_type_is_feature_completed_or_failed(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        _call_update(tmp_path, jsonl_path, outcome="completed")
        record = json.loads(jsonl_path.read_text().splitlines()[0])
        assert record["event_type"] in (
            "feature_completed", "feature_started", "progress_updated"
        ), f"Unexpected event_type: {record['event_type']}"

    def test_jsonl_record_has_required_fields(self, tmp_path):
        jsonl_path = tmp_path / ".bob" / "progress.jsonl"
        _call_update(tmp_path, jsonl_path)
        record = json.loads(jsonl_path.read_text().splitlines()[0])
        for field in ("timestamp", "event_type", "feature_id", "payload"):
            assert field in record, f"Missing required field: {field}"
