"""Tests for the unified telemetry exporter — run.jsonl."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.telemetry import emit_telemetry_line


REQUIRED_SCHEMA_FIELDS = [
    "run_id",
    "variant",
    "spec_id",
    "spec_version",
    "seed",
    "feature_id",
    "attempt_number",
    "completion_status",
    "cost_usd",
    "tokens_in",
    "tokens_out",
    "duration_ms",
    "hack_verdict",
    "confidence_predicted",
    "timestamp_utc",
]


class TestEmitTelemetryLineFileCreation:
    def test_creates_run_jsonl_in_bob3_dir(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="run-1", feature_id="feat-1")
        assert run_jsonl.exists()

    def test_creates_parent_directory_if_missing(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "nested" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="run-1")
        assert run_jsonl.parent.exists()


class TestEmitTelemetryLineSchema:
    def test_writes_valid_json_object(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="run-abc", feature_id="f-1")
        lines = run_jsonl.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert isinstance(record, dict)

    def test_all_schema_fields_present(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="run-abc", feature_id="f-1")
        record = json.loads(run_jsonl.read_text())
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in record, f"Missing required schema field: {field}"

    def test_run_id_is_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="my-run-42", feature_id="f-1")
        record = json.loads(run_jsonl.read_text())
        assert record["run_id"] == "my-run-42"

    def test_variant_reflects_ablation_mode(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
            patch.dict(os.environ, {"BOB3_ABLATION_MODE": "V1"}),
        ):
            emit_telemetry_line(run_id="r1", feature_id="f1")
        record = json.loads(run_jsonl.read_text())
        assert record["variant"] == "V1"

    def test_timestamp_utc_is_iso8601(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="r1")
        record = json.loads(run_jsonl.read_text())
        ts = record["timestamp_utc"]
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_extra_kwargs_included_in_record(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(
                run_id="r1",
                feature_id="feat-99",
                spec_id="spec-7",
                cost_usd=0.42,
                tokens_in=100,
                tokens_out=200,
                completion_status="completed",
                hack_verdict="clean",
                confidence_predicted=0.95,
            )
        record = json.loads(run_jsonl.read_text())
        assert record["feature_id"] == "feat-99"
        assert record["spec_id"] == "spec-7"
        assert record["cost_usd"] == pytest.approx(0.42)
        assert record["tokens_in"] == 100
        assert record["tokens_out"] == 200
        assert record["completion_status"] == "completed"
        assert record["hack_verdict"] == "clean"
        assert record["confidence_predicted"] == pytest.approx(0.95)


class TestEmitTelemetryLineAppends:
    def test_multiple_calls_produce_separate_lines(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="r1", feature_id="f1")
            emit_telemetry_line(run_id="r2", feature_id="f2")
            emit_telemetry_line(run_id="r3", feature_id="f3")
        lines = [l for l in run_jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        ids = [json.loads(l)["run_id"] for l in lines]
        assert ids == ["r1", "r2", "r3"]

    def test_appends_not_overwrites(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="first", completion_status="completed")
            emit_telemetry_line(run_id="second", completion_status="failed")
        lines = [l for l in run_jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["run_id"] == "first"


class TestEmitTelemetryLineDefaults:
    def test_none_defaults_for_optional_numeric_fields(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="r1")
        record = json.loads(run_jsonl.read_text())
        # Fields not provided must be present (possibly None/null)
        assert "cost_usd" in record
        assert "tokens_in" in record
        assert "tokens_out" in record
        assert "duration_ms" in record
        assert "hack_verdict" in record
        assert "confidence_predicted" in record

    def test_variant_defaults_to_ablation_env(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
            patch.dict(os.environ, {"BOB3_ABLATION_MODE": "V3"}),
        ):
            emit_telemetry_line(run_id="r1")
        record = json.loads(run_jsonl.read_text())
        assert record["variant"] == "V3"
