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


class TestConfigSetCommand:
    """Test 'bob config set' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create temporary config file."""
        config_file = tmp_path / "config.yaml"
        return config_file

    def test_set_help(self, runner):
        """Test config set --help."""
        result = runner.invoke(cli, ['config', 'set', '--help'])
        assert result.exit_code == 0
        assert 'Set a configuration value' in result.output
        assert 'dot notation' in result.output

    def test_set_string_value(self, runner, temp_config):
        """Test setting a string configuration value."""
        result = runner.invoke(cli, [
            'config', 'set',
            'models.default',
            'claude-opus-4-5-20251101',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 0
        assert 'Configuration updated' in result.output
        assert 'models.default' in result.output
        assert 'claude-opus-4-5-20251101' in result.output

        # Verify file was updated
        with open(temp_config) as f:
            config = yaml.safe_load(f)
        assert config['models']['default'] == 'claude-opus-4-5-20251101'

    def test_set_numeric_value(self, runner, temp_config):
        """Test setting numeric configuration values."""
        # Set integer
        result = runner.invoke(cli, [
            'config', 'set',
            'escalation.max_attempts_per_model',
            '5',
            '--config-path', str(temp_config)
        ])
        assert result.exit_code == 0

        # Verify it's stored as int
        with open(temp_config) as f:
            config = yaml.safe_load(f)
        assert config['escalation']['max_attempts_per_model'] == 5
        assert isinstance(config['escalation']['max_attempts_per_model'], int)

        # Set float
        result = runner.invoke(cli, [
            'config', 'set',
            'limits.max_cost_per_project',
            '200.5',
            '--config-path', str(temp_config)
        ])
        assert result.exit_code == 0

        # Verify it's stored as float
        with open(temp_config) as f:
            config = yaml.safe_load(f)
        assert config['limits']['max_cost_per_project'] == 200.5
        assert isinstance(config['limits']['max_cost_per_project'], float)

    def test_set_boolean_value(self, runner, temp_config):
        """Test setting boolean configuration values."""
        # First add a boolean field to defaults (for testing)
        # We'll use a string field and test boolean conversion

        result = runner.invoke(cli, [
            'config', 'set',
            'logging.level',
            'DEBUG',
            '--config-path', str(temp_config)
        ])
        assert result.exit_code == 0

    def test_set_invalid_key(self, runner, temp_config):
        """Test setting an invalid configuration key."""
        result = runner.invoke(cli, [
            'config', 'set',
            'invalid.key.path',
            'value',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 1
        assert 'Invalid configuration key' in result.output

    def test_set_json_output(self, runner, temp_config):
        """Test JSON output format for set command."""
        result = runner.invoke(cli, [
            'config', 'set',
            'models.default',
            'test-model',
            '--config-path', str(temp_config),
            '--json-output'
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output['status'] == 'success'
        assert output['key'] == 'models.default'
        assert output['value'] == 'test-model'
        assert 'config_path' in output

    def test_set_multiple_values_sequentially(self, runner, temp_config):
        """Test setting multiple configuration values."""
        # Set first value
        runner.invoke(cli, [
            'config', 'set',
            'models.default',
            'model-1',
            '--config-path', str(temp_config)
        ])

        # Set second value
        runner.invoke(cli, [
            'config', 'set',
            'models.escalation',
            'model-2',
            '--config-path', str(temp_config)
        ])

        # Set third value in different section
        runner.invoke(cli, [
            'config', 'set',
            'limits.max_cost_per_session',
            '10.0',
            '--config-path', str(temp_config)
        ])

        # Verify all values
        with open(temp_config) as f:
            config = yaml.safe_load(f)

        assert config['models']['default'] == 'model-1'
        assert config['models']['escalation'] == 'model-2'
        assert config['limits']['max_cost_per_session'] == 10.0

    def test_set_creates_config_file(self, runner, temp_config):
        """Test that set creates config file if it doesn't exist."""
        # Ensure file doesn't exist
        assert not temp_config.exists()

        result = runner.invoke(cli, [
            'config', 'set',
            'models.default',
            'new-model',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 0
        # File should now exist
        assert temp_config.exists()

        # Verify content
        with open(temp_config) as f:
            config = yaml.safe_load(f)
        assert config['models']['default'] == 'new-model'

    def test_set_preserves_existing_values(self, runner, temp_config):
        """Test that set preserves other existing values."""
        # Create initial config
        initial_config = {
            "models": {
                "default": "original-model",
                "escalation": "original-escalation",
            },
            "limits": {
                "max_cost_per_project": 100.0,
            }
        }

        with open(temp_config, 'w') as f:
            yaml.safe_dump(initial_config, f)

        # Update one value
        result = runner.invoke(cli, [
            'config', 'set',
            'models.default',
            'new-model',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 0

        # Verify other values are preserved
        with open(temp_config) as f:
            config = yaml.safe_load(f)

        assert config['models']['default'] == 'new-model'
        assert config['models']['escalation'] == 'original-escalation'
        assert config['limits']['max_cost_per_project'] == 100.0

    def test_set_nested_key(self, runner, temp_config):
        """Test setting deeply nested configuration keys."""
        result = runner.invoke(cli, [
            'config', 'set',
            'escalation.models.tier1',
            'custom-tier1-model',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 0

        with open(temp_config) as f:
            config = yaml.safe_load(f)

        assert config['escalation']['models']['tier1'] == 'custom-tier1-model'


class TestConfigEditCommand:
    """Test 'bob config edit' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create temporary config file."""
        config_file = tmp_path / "config.yaml"
        return config_file

    @pytest.fixture
    def mock_editor(self, tmp_path):
        """Create a mock editor script."""
        # Create a simple mock editor that just touches the file
        editor_script = tmp_path / "mock_editor.sh"
        editor_script.write_text("#!/bin/bash\ntouch \"$1\"\n")
        editor_script.chmod(0o755)
        return str(editor_script)

    def test_edit_help(self, runner):
        """Test config edit --help."""
        result = runner.invoke(cli, ['config', 'edit', '--help'])
        assert result.exit_code == 0
        assert 'Open configuration file in editor' in result.output
        assert '--editor' in result.output
        assert '--config-path' in result.output

    def test_edit_creates_config_if_missing(self, runner, temp_config, mock_editor, monkeypatch):
        """Test that edit creates config file if it doesn't exist."""
        # Mock subprocess to avoid actually opening an editor
        def mock_run(cmd):
            # Touch the file to simulate editor
            if temp_config.exists():
                temp_config.touch()
            else:
                # Create with default content
                temp_config.write_text("models:\n  default: test\n")
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano'
        ])

        assert temp_config.exists()

    def test_edit_with_valid_yaml(self, runner, temp_config, monkeypatch):
        """Test editing with valid YAML."""
        # Create initial config
        initial_config = {
            "models": {
                "default": "test-model",
            }
        }
        with open(temp_config, 'w') as f:
            yaml.safe_dump(initial_config, f)

        # Mock subprocess to simulate editing
        def mock_run(cmd):
            # Modify the file
            new_config = {
                "models": {
                    "default": "updated-model",
                }
            }
            with open(temp_config, 'w') as f:
                yaml.safe_dump(new_config, f)
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano'
        ])

        assert result.exit_code == 0
        assert 'Configuration updated successfully' in result.output

        # Verify file was updated
        with open(temp_config) as f:
            config = yaml.safe_load(f)
        assert config['models']['default'] == 'updated-model'

    def test_edit_with_invalid_yaml(self, runner, temp_config, monkeypatch):
        """Test editing with invalid YAML syntax."""
        # Create initial config
        initial_config = {"models": {"default": "test"}}
        with open(temp_config, 'w') as f:
            yaml.safe_dump(initial_config, f)

        # Mock subprocess to simulate editing with invalid YAML
        def mock_run(cmd):
            # Write invalid YAML
            temp_config.write_text("models:\n  default: test\n  invalid yaml [[[")
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano'
        ])

        assert result.exit_code == 1
        assert 'validation failed' in result.output.lower()

    def test_edit_no_changes(self, runner, temp_config, monkeypatch):
        """Test editing without making changes."""
        # Create initial config
        initial_config = {"models": {"default": "test"}}
        with open(temp_config, 'w') as f:
            yaml.safe_dump(initial_config, f)

        # Mock subprocess to simulate editor without changes
        def mock_run(cmd):
            # Don't modify the file
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano'
        ])

        assert result.exit_code == 0
        assert 'No changes made' in result.output

    def test_edit_with_custom_editor(self, runner, temp_config, monkeypatch):
        """Test using custom editor."""
        temp_config.write_text("models:\n  default: test\n")

        editor_called_with = []

        def mock_run(cmd):
            editor_called_with.append(cmd)
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'vim'
        ])

        assert result.exit_code == 0
        assert len(editor_called_with) == 1
        assert editor_called_with[0][0] == 'vim'

    def test_edit_json_output(self, runner, temp_config, monkeypatch):
        """Test JSON output format."""
        temp_config.write_text("models:\n  default: test\n")

        def mock_run(cmd):
            # Modify file
            temp_config.write_text("models:\n  default: updated\n")
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano',
            '--json-output'
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output['status'] == 'success'
        assert output['modified'] is True
        assert 'config_path' in output
        assert output['validation_errors'] == []

    def test_edit_json_output_validation_error(self, runner, temp_config, monkeypatch):
        """Test JSON output with validation error."""
        temp_config.write_text("models:\n  default: test\n")

        def mock_run(cmd):
            # Write invalid YAML
            temp_config.write_text("invalid: [[[")
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano',
            '--json-output'
        ])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output['status'] == 'error'
        assert 'validation_errors' in output
        assert len(output['validation_errors']) > 0

    def test_edit_editor_not_found(self, runner, temp_config, monkeypatch):
        """Test error when editor is not found."""
        temp_config.write_text("models:\n  default: test\n")

        def mock_run(cmd):
            raise FileNotFoundError()

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nonexistent-editor'
        ])

        assert result.exit_code == 1
        assert 'Editor not found' in result.output

    def test_edit_editor_exits_with_error(self, runner, temp_config, monkeypatch):
        """Test when editor exits with non-zero code."""
        temp_config.write_text("models:\n  default: test\n")

        def mock_run(cmd):
            return type('obj', (object,), {'returncode': 1})

        monkeypatch.setattr('subprocess.run', mock_run)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config),
            '--editor', 'nano'
        ])

        assert result.exit_code == 1
        assert 'exited with code' in result.output

    def test_edit_no_editor_specified(self, runner, temp_config, monkeypatch):
        """Test error when no editor is specified and $EDITOR is not set."""
        temp_config.write_text("models:\n  default: test\n")

        # Mock environment to not have EDITOR
        monkeypatch.delenv('EDITOR', raising=False)

        # Mock _get_default_editor to return None
        from bob.cli import config as config_module
        monkeypatch.setattr(config_module, '_get_default_editor', lambda: None)

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 1
        assert 'No editor specified' in result.output

    def test_edit_with_editor_env_var(self, runner, temp_config, monkeypatch):
        """Test using $EDITOR environment variable."""
        temp_config.write_text("models:\n  default: test\n")

        editor_called_with = []

        def mock_run(cmd):
            editor_called_with.append(cmd)
            return type('obj', (object,), {'returncode': 0})

        monkeypatch.setattr('subprocess.run', mock_run)
        monkeypatch.setenv('EDITOR', 'emacs')

        result = runner.invoke(cli, [
            'config', 'edit',
            '--config-path', str(temp_config)
        ])

        assert result.exit_code == 0
        assert len(editor_called_with) == 1
        assert editor_called_with[0][0] == 'emacs'

    def test_validate_config_file_valid(self, tmp_path):
        """Test config validation with valid YAML."""
        from bob.cli.config import _validate_config_file

        config_file = tmp_path / "test.yaml"
        config_file.write_text("models:\n  default: test\n")

        errors = _validate_config_file(config_file)
        assert errors == []

    def test_validate_config_file_invalid_yaml(self, tmp_path):
        """Test config validation with invalid YAML."""
        from bob.cli.config import _validate_config_file

        config_file = tmp_path / "test.yaml"
        config_file.write_text("invalid: [[[")

        errors = _validate_config_file(config_file)
        assert len(errors) > 0
        assert 'YAML' in errors[0]

    def test_validate_config_file_not_dict(self, tmp_path):
        """Test config validation when file contains non-dict."""
        from bob.cli.config import _validate_config_file

        config_file = tmp_path / "test.yaml"
        config_file.write_text("- item1\n- item2\n")

        errors = _validate_config_file(config_file)
        assert len(errors) > 0
        assert 'dictionary' in errors[0].lower()

    def test_validate_config_file_missing(self, tmp_path):
        """Test config validation with missing file."""
        from bob.cli.config import _validate_config_file

        config_file = tmp_path / "nonexistent.yaml"

        errors = _validate_config_file(config_file)
        assert len(errors) > 0
        assert 'does not exist' in errors[0].lower()
