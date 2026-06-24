"""Tests for BOB_ABLATION_MODE environment variable and CLI flag (F-ablation)."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from bob.ablation import AblationMode, get_ablation_mode


class TestAblationModeEnum:
    """Verify the AblationMode enum has all required members."""

    def test_has_v_minus_1(self):
        assert hasattr(AblationMode, "V_1")

    def test_has_v0(self):
        assert hasattr(AblationMode, "V0")

    def test_has_v1(self):
        assert hasattr(AblationMode, "V1")

    def test_has_v2(self):
        assert hasattr(AblationMode, "V2")

    def test_has_v3(self):
        assert hasattr(AblationMode, "V3")

    def test_v_minus_1_value(self):
        assert AblationMode.V_1.value == "V-1"

    def test_v0_value(self):
        assert AblationMode.V0.value == "V0"

    def test_v1_value(self):
        assert AblationMode.V1.value == "V1"

    def test_v2_value(self):
        assert AblationMode.V2.value == "V2"

    def test_v3_value(self):
        assert AblationMode.V3.value == "V3"

    def test_all_members_count(self):
        assert len(AblationMode) == 5


class TestGetAblationMode:
    """Verify get_ablation_mode reads from environment correctly."""

    def test_default_is_v0(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BOB_ABLATION_MODE", None)
            mode = get_ablation_mode()
        assert mode is AblationMode.V0

    def test_env_var_v_minus_1(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "V-1"}):
            assert get_ablation_mode() is AblationMode.V_1

    def test_env_var_v0(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "V0"}):
            assert get_ablation_mode() is AblationMode.V0

    def test_env_var_v1(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "V1"}):
            assert get_ablation_mode() is AblationMode.V1

    def test_env_var_v2(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "V2"}):
            assert get_ablation_mode() is AblationMode.V2

    def test_env_var_v3(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "V3"}):
            assert get_ablation_mode() is AblationMode.V3

    def test_invalid_env_var_raises(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "INVALID"}):
            with pytest.raises(ValueError, match="BOB_ABLATION_MODE"):
                get_ablation_mode()

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "v1"}):
            assert get_ablation_mode() is AblationMode.V1

    def test_v_minus_1_case_insensitive(self):
        with patch.dict(os.environ, {"BOB_ABLATION_MODE": "v-1"}):
            assert get_ablation_mode() is AblationMode.V_1


class TestAblationModeConfig:
    """Verify each mode produces appropriate config constraints."""

    def test_v_minus_1_disables_ai(self):
        from bob.ablation import get_mode_config
        config = get_mode_config(AblationMode.V_1)
        assert config["ai_assistance"] is False

    def test_v0_is_baseline(self):
        from bob.ablation import get_mode_config
        config = get_mode_config(AblationMode.V0)
        assert config["ai_assistance"] is True
        assert config["memory"] is False
        assert config["research"] is False

    def test_v1_enables_memory(self):
        from bob.ablation import get_mode_config
        config = get_mode_config(AblationMode.V1)
        assert config["ai_assistance"] is True
        assert config["memory"] is True
        assert config["research"] is False

    def test_v2_enables_research(self):
        from bob.ablation import get_mode_config
        config = get_mode_config(AblationMode.V2)
        assert config["ai_assistance"] is True
        assert config["memory"] is True
        assert config["research"] is True
        assert config["sub_agents"] is False

    def test_v3_enables_all(self):
        from bob.ablation import get_mode_config
        config = get_mode_config(AblationMode.V3)
        assert config["ai_assistance"] is True
        assert config["memory"] is True
        assert config["research"] is True
        assert config["sub_agents"] is True


class TestAblationModeProgressEvents:
    """Verify ablation mode is recorded in telemetry."""

    def test_telemetry_label_v_minus_1(self):
        from bob.ablation import get_telemetry_label
        assert get_telemetry_label(AblationMode.V_1) == "V-1"

    def test_telemetry_label_v0(self):
        from bob.ablation import get_telemetry_label
        assert get_telemetry_label(AblationMode.V0) == "V0"

    def test_telemetry_label_v3(self):
        from bob.ablation import get_telemetry_label
        assert get_telemetry_label(AblationMode.V3) == "V3"


class TestCLIAblationFlag:
    """Verify the --ablation-mode CLI flag works correctly."""

    def test_cli_run_accepts_ablation_mode(self):
        from click.testing import CliRunner
        from bob.cli import main

        runner = CliRunner()
        # Just check the option is recognized (don't actually run)
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "--ablation-mode" in result.output

    def test_cli_ablation_mode_choices(self):
        from click.testing import CliRunner
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        # All valid modes should appear in help
        assert "V0" in result.output
