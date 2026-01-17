#!/usr/bin/env python3
"""Tests for configuration management."""

import os
from pathlib import Path

import pytest
import yaml

from bob.config import (
    DEFAULT_CONFIG,
    ConfigManager,
    get_config_manager,
    load_config,
)


class TestConfigManager:
    """Test ConfigManager class."""

    @pytest.fixture
    def temp_config_file(self, tmp_path):
        """Create a temporary config file."""
        config_file = tmp_path / "config.yaml"
        return config_file

    def test_init_default_path(self):
        """Test initialization with default path."""
        manager = ConfigManager()
        assert manager.config_path == Path.home() / ".bob" / "config.yaml"

    def test_init_custom_path(self, temp_config_file):
        """Test initialization with custom path."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager.config_path == temp_config_file

    def test_load_nonexistent_file_returns_defaults(self, temp_config_file):
        """Test loading from nonexistent file returns default config."""
        manager = ConfigManager(config_path=temp_config_file)
        config = manager.load()
        assert config["models"]["default"] == DEFAULT_CONFIG["models"]["default"]
        assert config["api"]["anthropic_api_key"] == DEFAULT_CONFIG["api"]["anthropic_api_key"]

    def test_load_from_file(self, temp_config_file):
        """Test loading configuration from file."""
        # Create a config file
        test_config = {
            "models": {
                "default": "custom-model",
                "escalation": "custom-escalation-model",
            }
        }

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(test_config, f)

        manager = ConfigManager(config_path=temp_config_file)
        config = manager.load()

        assert config["models"]["default"] == "custom-model"
        assert config["models"]["escalation"] == "custom-escalation-model"

    def test_load_merges_with_defaults(self, temp_config_file):
        """Test that partial config is merged with defaults."""
        # Create a partial config file
        partial_config = {
            "models": {
                "default": "custom-model",
            }
        }

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(partial_config, f)

        manager = ConfigManager(config_path=temp_config_file)
        config = manager.load()

        # Custom value
        assert config["models"]["default"] == "custom-model"
        # Default values still present
        assert "escalation" in config["models"]
        assert "database" in config
        assert "logging" in config

    def test_save(self, temp_config_file):
        """Test saving configuration to file."""
        manager = ConfigManager(config_path=temp_config_file)

        test_config = {
            "models": {
                "default": "saved-model",
            }
        }

        manager.save(test_config)

        # Verify file was created
        assert temp_config_file.exists()

        # Load and verify content
        with open(temp_config_file, 'r') as f:
            loaded = yaml.safe_load(f)

        assert loaded["models"]["default"] == "saved-model"

    def test_save_creates_directory(self, tmp_path):
        """Test that save creates parent directory if it doesn't exist."""
        nested_path = tmp_path / "nested" / "dir" / "config.yaml"
        manager = ConfigManager(config_path=nested_path)

        manager.save({"test": "value"})

        assert nested_path.exists()
        assert nested_path.parent.exists()

    def test_get_with_dot_notation(self, temp_config_file):
        """Test getting values with dot notation."""
        config = {
            "models": {
                "default": "test-model",
            },
            "limits": {
                "max_cost_per_project": 50.0,
            }
        }

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(config, f)

        manager = ConfigManager(config_path=temp_config_file)

        assert manager.get("models.default") == "test-model"
        assert manager.get("limits.max_cost_per_project") == 50.0

    def test_get_with_default(self, temp_config_file):
        """Test get returns default for missing keys."""
        manager = ConfigManager(config_path=temp_config_file)

        assert manager.get("nonexistent.key", "default_value") == "default_value"

    def test_set_with_dot_notation(self, temp_config_file):
        """Test setting values with dot notation."""
        manager = ConfigManager(config_path=temp_config_file)

        manager.set("models.default", "new-model")
        manager.set("limits.max_cost_per_project", 75.0)

        assert manager.get("models.default") == "new-model"
        assert manager.get("limits.max_cost_per_project") == 75.0

    def test_set_creates_nested_keys(self, temp_config_file):
        """Test set creates nested keys if they don't exist."""
        manager = ConfigManager(config_path=temp_config_file)

        manager.set("new.nested.key", "value")

        assert manager.get("new.nested.key") == "value"

    def test_get_all(self, temp_config_file):
        """Test getting entire configuration."""
        test_config = {"test": "value"}

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(test_config, f)

        manager = ConfigManager(config_path=temp_config_file)
        config = manager.get_all()

        # Should have defaults merged in
        assert "models" in config
        assert "database" in config

    def test_reload(self, temp_config_file):
        """Test reloading configuration from file."""
        # Create initial config
        initial_config = {"models": {"default": "model-v1"}}

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(initial_config, f)

        manager = ConfigManager(config_path=temp_config_file)
        assert manager.get("models.default") == "model-v1"

        # Update file
        updated_config = {"models": {"default": "model-v2"}}

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(updated_config, f)

        # Reload
        manager.reload()
        assert manager.get("models.default") == "model-v2"

    def test_config_exists(self, temp_config_file):
        """Test checking if config file exists."""
        manager = ConfigManager(config_path=temp_config_file)

        assert not manager.config_exists()

        # Create file
        temp_config_file.write_text("test: value")

        assert manager.config_exists()

    def test_create_default_config(self, temp_config_file):
        """Test creating default config file."""
        manager = ConfigManager(config_path=temp_config_file)

        assert not temp_config_file.exists()

        manager.create_default_config()

        assert temp_config_file.exists()

        # Verify it has default values
        with open(temp_config_file, 'r') as f:
            config = yaml.safe_load(f)

        assert config["models"]["default"] == DEFAULT_CONFIG["models"]["default"]

    def test_create_default_config_doesnt_overwrite(self, temp_config_file):
        """Test that create_default_config doesn't overwrite existing file."""
        # Create file with custom content
        custom_config = {"custom": "value"}

        with open(temp_config_file, 'w') as f:
            yaml.safe_dump(custom_config, f)

        manager = ConfigManager(config_path=temp_config_file)
        manager.create_default_config()

        # Should not have been overwritten
        with open(temp_config_file, 'r') as f:
            config = yaml.safe_load(f)

        assert config["custom"] == "value"


class TestEnvVarExpansion:
    """Test environment variable expansion."""

    def test_expand_env_vars_basic(self, tmp_path):
        """Test basic environment variable expansion."""
        os.environ["TEST_VAR"] = "test_value"

        config_file = tmp_path / "config.yaml"
        test_config = {
            "api": {
                "key": "${TEST_VAR}",
            }
        }

        with open(config_file, 'w') as f:
            yaml.safe_dump(test_config, f)

        manager = ConfigManager(config_path=config_file)
        config = manager.load()

        assert config["api"]["key"] == "test_value"

        # Cleanup
        del os.environ["TEST_VAR"]

    def test_expand_env_vars_default_config(self, tmp_path):
        """Test env var expansion in default config."""
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-key-123"

        config_file = tmp_path / "nonexistent.yaml"
        manager = ConfigManager(config_path=config_file)
        config = manager.load()

        assert config["api"]["anthropic_api_key"] == "sk-test-key-123"

        # Cleanup
        del os.environ["ANTHROPIC_API_KEY"]

    def test_expand_env_vars_nested(self, tmp_path):
        """Test env var expansion in nested structures."""
        os.environ["MODEL_NAME"] = "my-model"

        config_file = tmp_path / "config.yaml"
        test_config = {
            "models": {
                "default": "${MODEL_NAME}",
                "escalation": "static-model",
            }
        }

        with open(config_file, 'w') as f:
            yaml.safe_dump(test_config, f)

        manager = ConfigManager(config_path=config_file)
        config = manager.load()

        assert config["models"]["default"] == "my-model"
        assert config["models"]["escalation"] == "static-model"

        # Cleanup
        del os.environ["MODEL_NAME"]


class TestFactoryFunctions:
    """Test factory functions."""

    def test_get_config_manager(self):
        """Test get_config_manager factory function."""
        manager = get_config_manager()
        assert isinstance(manager, ConfigManager)

    def test_get_config_manager_custom_path(self, tmp_path):
        """Test get_config_manager with custom path."""
        custom_path = tmp_path / "custom.yaml"
        manager = get_config_manager(config_path=custom_path)
        assert manager.config_path == custom_path

    def test_load_config(self):
        """Test load_config function."""
        config = load_config()
        assert isinstance(config, dict)
        assert "models" in config
        assert "database" in config


class TestDefaultConfig:
    """Test the default configuration."""

    def test_default_config_has_required_sections(self):
        """Test that default config has all required sections."""
        assert "models" in DEFAULT_CONFIG
        assert "api" in DEFAULT_CONFIG
        assert "database" in DEFAULT_CONFIG
        assert "logging" in DEFAULT_CONFIG
        assert "limits" in DEFAULT_CONFIG
        assert "escalation" in DEFAULT_CONFIG

    def test_default_config_models(self):
        """Test default model configuration."""
        assert "default" in DEFAULT_CONFIG["models"]
        assert "escalation" in DEFAULT_CONFIG["models"]
        assert "claude" in DEFAULT_CONFIG["models"]["default"]

    def test_default_config_limits(self):
        """Test default cost limits."""
        assert DEFAULT_CONFIG["limits"]["max_cost_per_project"] == 100.0
        assert DEFAULT_CONFIG["limits"]["max_cost_per_session"] == 5.0
        assert DEFAULT_CONFIG["limits"]["warn_at_percent"] == 80

    def test_default_config_database(self):
        """Test default database configuration."""
        assert DEFAULT_CONFIG["database"]["type"] == "sqlite"
        assert "~/.bob/bob.db" in DEFAULT_CONFIG["database"]["path"]

    def test_default_config_logging(self):
        """Test default logging configuration."""
        assert DEFAULT_CONFIG["logging"]["level"] == "INFO"
        assert DEFAULT_CONFIG["logging"]["format"] == "json"
