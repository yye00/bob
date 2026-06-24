"""Tests for src/bob3/external_baselines.py — external baseline runners.

Covers:
- BaselineResult dataclass fields
- run_aider_baseline: telemetry schema, timing, not_installed path
- run_claude_code_baseline: telemetry schema, timing, not_installed path
- variant labels in telemetry (AIDER_VARIANT, CLAUDE_CODE_VARIANT)
- deterministic run_id generation
- emit_telemetry=False suppression
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from bob3.external_baselines import (
    AIDER_VARIANT,
    CLAUDE_CODE_VARIANT,
    BaselineResult,
    _make_run_id,
    run_aider_baseline,
    run_claude_code_baseline,
)
from bob3.telemetry import _SCHEMA_DEFAULTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_TELEMETRY_FIELDS = list(_SCHEMA_DEFAULTS.keys())


def _read_records(run_jsonl: Path) -> list[dict]:
    if not run_jsonl.exists():
        return []
    return [json.loads(line) for line in run_jsonl.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# BaselineResult
# ---------------------------------------------------------------------------


class TestBaselineResult:
    def test_fields_accessible(self):
        r = BaselineResult(
            run_id="abc",
            variant="aider",
            completion_status="completed",
            duration_ms=123,
            returncode=0,
            stdout="out",
            stderr="err",
        )
        assert r.run_id == "abc"
        assert r.variant == "aider"
        assert r.completion_status == "completed"
        assert r.duration_ms == 123
        assert r.returncode == 0
        assert r.stdout == "out"
        assert r.stderr == "err"
        assert r.tool_version is None
        assert r.extra == {}

    def test_extra_defaults_to_empty_dict(self):
        r = BaselineResult(
            run_id="x", variant="v", completion_status="ok",
            duration_ms=0, returncode=0, stdout="", stderr="",
        )
        assert isinstance(r.extra, dict)


# ---------------------------------------------------------------------------
# _make_run_id
# ---------------------------------------------------------------------------


class TestMakeRunId:
    def test_returns_string(self):
        rid = _make_run_id("aider", "spec-1", 42)
        assert isinstance(rid, str)

    def test_deterministic(self):
        r1 = _make_run_id("aider", "spec-1", 42)
        r2 = _make_run_id("aider", "spec-1", 42)
        assert r1 == r2

    def test_differs_by_variant(self):
        r1 = _make_run_id("aider", "spec-1", 1)
        r2 = _make_run_id("claude-code", "spec-1", 1)
        assert r1 != r2

    def test_differs_by_spec(self):
        r1 = _make_run_id("aider", "spec-1", 1)
        r2 = _make_run_id("aider", "spec-2", 1)
        assert r1 != r2

    def test_differs_by_seed(self):
        r1 = _make_run_id("aider", "spec-1", 1)
        r2 = _make_run_id("aider", "spec-1", 2)
        assert r1 != r2

    def test_length_16(self):
        rid = _make_run_id("aider", "spec-x", 0)
        assert len(rid) == 16


# ---------------------------------------------------------------------------
# Variant constants
# ---------------------------------------------------------------------------


class TestVariantConstants:
    def test_aider_variant_label(self):
        assert AIDER_VARIANT == "aider"

    def test_claude_code_variant_label(self):
        assert CLAUDE_CODE_VARIANT == "claude-code"


# ---------------------------------------------------------------------------
# run_aider_baseline — not installed path
# ---------------------------------------------------------------------------


class TestRunAiderBaselineNotInstalled:
    def test_not_installed_completion_status(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("fix the bug", spec_id="s1", seed=0)

        assert result.completion_status == "not_installed"

    def test_not_installed_duration_is_zero(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("fix it", spec_id="s1", seed=0)

        assert result.duration_ms == 0

    def test_not_installed_emits_telemetry(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("fix it", spec_id="spec-aider", seed=3)

        records = _read_records(run_jsonl)
        assert len(records) == 1
        assert records[0]["completion_status"] == "not_installed"

    def test_not_installed_telemetry_has_aider_variant(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        assert records[0]["variant"] == AIDER_VARIANT

    def test_not_installed_no_telemetry_when_suppressed(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0, emit_telemetry=False)

        assert not run_jsonl.exists()

    def test_not_installed_variant_field(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("prompt", spec_id="s", seed=0)

        assert result.variant == AIDER_VARIANT


# ---------------------------------------------------------------------------
# run_aider_baseline — installed path (mocked subprocess)
# ---------------------------------------------------------------------------


def _make_completed_process(returncode: int = 0, stdout: str = "ok", stderr: str = "") -> subprocess.CompletedProcess:
    p = subprocess.CompletedProcess(args=[], returncode=returncode)
    p.stdout = stdout
    p.stderr = stderr
    return p


class TestRunAiderBaselineInstalled:
    def test_success_completion_status(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("add feature", spec_id="s1", seed=1)

        assert result.completion_status == "completed"

    def test_failure_completion_status(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(1)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("add feature", spec_id="s1", seed=1)

        assert result.completion_status == "failed"

    def test_returncode_captured(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(42)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("prompt", spec_id="s", seed=0)

        assert result.returncode == 42

    def test_stdout_captured(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0, stdout="hello aider")),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("prompt", spec_id="s", seed=0)

        assert result.stdout == "hello aider"

    def test_stderr_captured(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0, stderr="warn!")),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("prompt", spec_id="s", seed=0)

        assert result.stderr == "warn!"

    def test_emits_telemetry_line(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("add feature", spec_id="spec-aider", seed=7)

        records = _read_records(run_jsonl)
        assert len(records) == 1

    def test_telemetry_variant_is_aider(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        assert records[0]["variant"] == AIDER_VARIANT

    def test_telemetry_spec_id_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="my-spec", seed=0)

        records = _read_records(run_jsonl)
        assert records[0]["spec_id"] == "my-spec"

    def test_telemetry_seed_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=99)

        records = _read_records(run_jsonl)
        assert records[0]["seed"] == 99

    def test_telemetry_feature_id_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0, feature_id="feat-xyz")

        records = _read_records(run_jsonl)
        assert records[0]["feature_id"] == "feat-xyz"

    def test_telemetry_has_all_required_schema_fields(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        for field in REQUIRED_TELEMETRY_FIELDS:
            assert field in records[0], f"Missing schema field: {field}"

    def test_no_telemetry_when_suppressed(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0, emit_telemetry=False)

        assert not run_jsonl.exists()

    def test_duration_ms_is_non_negative(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("prompt", spec_id="s", seed=0)

        assert result.duration_ms >= 0

    def test_telemetry_duration_matches_result(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_aider_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        assert records[0]["duration_ms"] == result.duration_ms

    def test_telemetry_attempt_number_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/bin/aider"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("prompt", spec_id="s", seed=0, attempt_number=3)

        records = _read_records(run_jsonl)
        assert records[0]["attempt_number"] == 3


# ---------------------------------------------------------------------------
# run_claude_code_baseline — not installed path
# ---------------------------------------------------------------------------


class TestRunClaudeCodeBaselineNotInstalled:
    def test_not_installed_completion_status(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_claude_code_baseline("fix bug", spec_id="s", seed=0)

        assert result.completion_status == "not_installed"

    def test_not_installed_variant_is_claude_code(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_claude_code_baseline("fix bug", spec_id="s", seed=0)

        assert result.variant == CLAUDE_CODE_VARIANT

    def test_not_installed_emits_telemetry(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        assert len(records) == 1
        assert records[0]["variant"] == CLAUDE_CODE_VARIANT

    def test_not_installed_no_telemetry_when_suppressed(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="s", seed=0, emit_telemetry=False)

        assert not run_jsonl.exists()


# ---------------------------------------------------------------------------
# run_claude_code_baseline — installed path (mocked subprocess)
# ---------------------------------------------------------------------------


class TestRunClaudeCodeBaselineInstalled:
    def test_success_completion_status(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_claude_code_baseline("add feature", spec_id="s", seed=0)

        assert result.completion_status == "completed"

    def test_failure_completion_status(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(1)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_claude_code_baseline("add feature", spec_id="s", seed=0)

        assert result.completion_status == "failed"

    def test_telemetry_variant_is_claude_code(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        assert records[0]["variant"] == CLAUDE_CODE_VARIANT

    def test_telemetry_has_all_required_schema_fields(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        for field in REQUIRED_TELEMETRY_FIELDS:
            assert field in records[0], f"Missing schema field: {field}"

    def test_telemetry_spec_id_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="spec-cc", seed=0)

        records = _read_records(run_jsonl)
        assert records[0]["spec_id"] == "spec-cc"

    def test_telemetry_seed_recorded(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="s", seed=55)

        records = _read_records(run_jsonl)
        assert records[0]["seed"] == 55

    def test_stdout_captured(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0, stdout="claude output")),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_claude_code_baseline("prompt", spec_id="s", seed=0)

        assert result.stdout == "claude output"

    def test_no_telemetry_when_suppressed(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_claude_code_baseline("prompt", spec_id="s", seed=0, emit_telemetry=False)

        assert not run_jsonl.exists()

    def test_duration_ms_non_negative(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value="/usr/local/bin/claude"),
            patch("bob3.external_baselines.subprocess.run", return_value=_make_completed_process(0)),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            result = run_claude_code_baseline("prompt", spec_id="s", seed=0)

        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# Sweep orchestrator integration: same run.jsonl, distinct variants
# ---------------------------------------------------------------------------


class TestSweepIntegration:
    def test_aider_and_claude_code_share_run_jsonl(self, tmp_path):
        """Both runners append to the same run.jsonl so sweep can compare them."""
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("task", spec_id="s", seed=1)
            run_claude_code_baseline("task", spec_id="s", seed=1)

        records = _read_records(run_jsonl)
        assert len(records) == 2
        variants = {r["variant"] for r in records}
        assert AIDER_VARIANT in variants
        assert CLAUDE_CODE_VARIANT in variants

    def test_aider_and_claude_code_have_distinct_run_ids(self, tmp_path):
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            r1 = run_aider_baseline("task", spec_id="s", seed=1)
            r2 = run_claude_code_baseline("task", spec_id="s", seed=1)

        assert r1.run_id != r2.run_id

    def test_same_spec_same_seed_same_variant_gives_same_run_id(self, tmp_path):
        """Determinism: identical inputs → identical run_id (idempotent)."""
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            r1 = run_aider_baseline("task", spec_id="spec-x", seed=7)
            r2 = run_aider_baseline("task", spec_id="spec-x", seed=7)

        assert r1.run_id == r2.run_id

    def test_telemetry_timestamp_utc_present(self, tmp_path):
        from datetime import datetime
        run_jsonl = tmp_path / ".bob3" / "run.jsonl"
        with (
            patch("bob3.external_baselines.shutil.which", return_value=None),
            patch("bob3.telemetry.get_run_jsonl_path", return_value=run_jsonl),
        ):
            run_aider_baseline("task", spec_id="s", seed=0)

        records = _read_records(run_jsonl)
        ts = records[0]["timestamp_utc"]
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None
