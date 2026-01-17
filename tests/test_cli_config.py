#!/usr/bin/env python3
"""Tests for config CLI commands."""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from bob.cli.main import cli


class TestConfigShowCommand:
    """Test 'bob config show' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create temporary config file."""
        config_file = tmp_path / "config.yaml"
        return config_file

    def test_show_help(self, runner):
        """Test config show --help."""
        result = runner.invoke(cli, ['config', 'show', '--help'])
        assert result.exit_code == 0
        assert 'Display current configuration' in result.output
        assert '--json-output' in result.output
        assert '--config-path' in result.output

    def test_show_default_config(self, runner, temp_config):
        """Test showing default config when file doesn't exist."""
        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert 'default' in result.output.lower() or 'no config file' in result.output.lower()
        # Should show config sections
        assert 'Models' in result.output or 'models' in result.output.lower()

    def test_show_custom_config(self, runner, temp_config):
        """Test showing custom config from file."""
        # Create custom config
        custom_config = {
            "models": {
                "default": "custom-model",
                "escalation": "custom-escalation",
            },
            "limits": {
                "max_cost_per_project": 50.0,
                "max_cost_per_session": 2.5,
                "warn_at_percent": 75,
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(custom_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert 'custom-model' in result.output
        assert 'custom-escalation' in result.output

    def test_show_json_output(self, runner, temp_config):
        """Test JSON output format."""
        # Create config
        test_config = {
            "models": {
                "default": "test-model",
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config), '--json-output'])
        assert result.exit_code == 0

        # Parse JSON
        output_data = json.loads(result.output)
        assert "config_path" in output_data
        assert "config_exists" in output_data
        assert "config" in output_data
        assert output_data["config_exists"] is True
        assert output_data["config"]["models"]["default"] == "test-model"

    def test_show_json_output_nonexistent_file(self, runner, temp_config):
        """Test JSON output when config file doesn't exist."""
        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config), '--json-output'])
        assert result.exit_code == 0

        output_data = json.loads(result.output)
        assert output_data["config_exists"] is False
        # Should still have default config
        assert "models" in output_data["config"]
        assert "database" in output_data["config"]

    def test_show_displays_models_section(self, runner, temp_config):
        """Test that show displays models section."""
        test_config = {
            "models": {
                "default": "model-a",
                "escalation": "model-b",
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert 'model-a' in result.output
        assert 'model-b' in result.output

    def test_show_displays_database_section(self, runner, temp_config):
        """Test that show displays database section."""
        test_config = {
            "database": {
                "type": "sqlite",
                "path": "/custom/path/db.sqlite",
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert 'sqlite' in result.output
        assert '/custom/path/db.sqlite' in result.output

    def test_show_displays_limits_section(self, runner, temp_config):
        """Test that show displays cost limits section."""
        test_config = {
            "limits": {
                "max_cost_per_project": 75.50,
                "max_cost_per_session": 3.25,
                "warn_at_percent": 85,
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert '75.50' in result.output
        assert '3.25' in result.output
        assert '85' in result.output

    def test_show_displays_logging_section(self, runner, temp_config):
        """Test that show displays logging section."""
        test_config = {
            "logging": {
                "level": "DEBUG",
                "format": "text",
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert 'DEBUG' in result.output
        assert 'text' in result.output

    def test_show_displays_escalation_section(self, runner, temp_config):
        """Test that show displays escalation section."""
        test_config = {
            "escalation": {
                "max_attempts_per_model": 5,
                "models": {
                    "tier1": "tier1-model",
                    "tier2": "tier2-model",
                }
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert '5' in result.output
        assert 'tier1-model' in result.output
        assert 'tier2-model' in result.output

    def test_show_masks_api_key(self, runner, temp_config):
        """Test that API keys are masked in output."""
        test_config = {
            "api": {
                "anthropic_api_key": "sk-ant-1234567890abcdefghijklmnopqrstuvwxyz",
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        # Should not show full key
        assert 'sk-ant-1234567890abcdefghijklmnopqrstuvwxyz' not in result.output
        # Should show masked version
        assert '...' in result.output or '***' in result.output

    def test_show_with_env_var_placeholder(self, runner, temp_config):
        """Test showing config with environment variable placeholder."""
        test_config = {
            "api": {
                "anthropic_api_key": "${ANTHROPIC_API_KEY}",
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(test_config, f)

        result = runner.invoke(cli, ['config', 'show', '--config-path', str(temp_config)])
        assert result.exit_code == 0
        assert 'ANTHROPIC_API_KEY' in result.output


class TestConfigCommandGroup:
    """Test config command group."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    def test_config_help(self, runner):
        """Test 'bob config --help'."""
        result = runner.invoke(cli, ['config', '--help'])
        assert result.exit_code == 0
        assert 'Manage configuration' in result.output
        assert 'show' in result.output

    def test_config_without_subcommand(self, runner):
        """Test 'bob config' without subcommand shows help."""
        result = runner.invoke(cli, ['config'])
        # Should show help or error
        assert 'show' in result.output or 'Commands' in result.output
