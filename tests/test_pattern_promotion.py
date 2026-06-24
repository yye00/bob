"""Tests for Pattern-promotion config knob (promote_on_n).

Covers:
- get_promote_on_n reads BOB_PROMOTE_ON_N env var (default 3)
- Ablation switch exposes promote_on_n per mode
- Telemetry schema includes promote_on_n
"""
import os
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.learnings import get_promote_on_n
from bob.ablation import get_mode_config, AblationMode


class TestGetPromoteOnN:
    """Tests for bob.learnings.get_promote_on_n."""

    def test_default_is_three(self):
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items() if k != "BOB_PROMOTE_ON_N"}
            with patch.dict(os.environ, env, clear=True):
                assert get_promote_on_n() == 3

    def test_reads_env_var(self):
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "5"}):
            assert get_promote_on_n() == 5

    def test_env_var_value_one(self):
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "1"}):
            assert get_promote_on_n() == 1

    def test_env_var_value_ten(self):
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "10"}):
            assert get_promote_on_n() == 10

    def test_returns_int(self):
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "7"}):
            result = get_promote_on_n()
            assert isinstance(result, int)

    def test_invalid_value_raises(self):
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "not_a_number"}):
            with pytest.raises(ValueError):
                get_promote_on_n()

    def test_zero_is_valid(self):
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "0"}):
            assert get_promote_on_n() == 0

    def test_unset_env_returns_default(self):
        env_without = {k: v for k, v in os.environ.items() if k != "BOB_PROMOTE_ON_N"}
        with patch.dict(os.environ, env_without, clear=True):
            assert get_promote_on_n() == 3


class TestAblationPromoteOnN:
    """Tests that ablation mode config includes promote_on_n."""

    def test_v1_has_promote_on_n(self):
        config = get_mode_config(AblationMode.V1)
        assert "promote_on_n" in config

    def test_v2_has_promote_on_n(self):
        config = get_mode_config(AblationMode.V2)
        assert "promote_on_n" in config

    def test_v3_has_promote_on_n(self):
        config = get_mode_config(AblationMode.V3)
        assert "promote_on_n" in config

    def test_v0_has_promote_on_n(self):
        config = get_mode_config(AblationMode.V0)
        assert "promote_on_n" in config

    def test_v_neg1_has_promote_on_n(self):
        config = get_mode_config(AblationMode.V_1)
        assert "promote_on_n" in config

    def test_v1_promote_on_n_is_not_none(self):
        config = get_mode_config(AblationMode.V1)
        assert config["promote_on_n"] is not None

    def test_v0_promotion_disabled(self):
        """V0 mode should ablate promotion (promote_on_n=None disables it)."""
        config = get_mode_config(AblationMode.V0)
        # V0 has no memory, so promotion is meaningless — should be None/disabled
        assert config["promote_on_n"] is None

    def test_v_neg1_promotion_disabled(self):
        """V-1 mode should ablate promotion."""
        config = get_mode_config(AblationMode.V_1)
        assert config["promote_on_n"] is None

    def test_v1_v2_v3_use_env_value(self):
        """V1/V2/V3 modes that have memory enabled should use the configured value."""
        with patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "7"}):
            for mode in (AblationMode.V1, AblationMode.V2, AblationMode.V3):
                config = get_mode_config(mode)
                assert config["promote_on_n"] == 7


class TestTelemetryPromoteOnN:
    """Tests that telemetry records promote_on_n."""

    def test_telemetry_schema_has_promote_on_n(self, tmp_path):
        """emit_telemetry_line writes promote_on_n field to the JSONL record."""
        from bob.telemetry import emit_telemetry_line, _DEFAULT_RUN_JSONL_PATH
        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        with (
            patch("bob.telemetry._DEFAULT_RUN_JSONL_PATH", run_jsonl),
            patch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl),
            patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "4"}),
        ):
            run_jsonl.parent.mkdir(parents=True, exist_ok=True)
            emit_telemetry_line("test-run-id")
        records = [json.loads(line) for line in run_jsonl.read_text().splitlines() if line.strip()]
        assert len(records) == 1
        assert "promote_on_n" in records[0]

    def test_telemetry_promote_on_n_value_matches_env(self, tmp_path):
        from bob.telemetry import emit_telemetry_line
        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        with (
            patch("bob.telemetry._DEFAULT_RUN_JSONL_PATH", run_jsonl),
            patch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl),
            patch.dict(os.environ, {"BOB_PROMOTE_ON_N": "6"}),
        ):
            run_jsonl.parent.mkdir(parents=True, exist_ok=True)
            emit_telemetry_line("test-run-id-2")
        records = [json.loads(line) for line in run_jsonl.read_text().splitlines() if line.strip()]
        assert records[0]["promote_on_n"] == 6

    def test_telemetry_default_promote_on_n(self, tmp_path):
        from bob.telemetry import emit_telemetry_line
        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        env_without = {k: v for k, v in os.environ.items() if k != "BOB_PROMOTE_ON_N"}
        with (
            patch("bob.telemetry._DEFAULT_RUN_JSONL_PATH", run_jsonl),
            patch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl),
            patch.dict(os.environ, env_without, clear=True),
        ):
            run_jsonl.parent.mkdir(parents=True, exist_ok=True)
            emit_telemetry_line("test-run-id-3")
        records = [json.loads(line) for line in run_jsonl.read_text().splitlines() if line.strip()]
        assert records[0]["promote_on_n"] == 3
