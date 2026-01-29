#!/usr/bin/env python3
"""
Global configuration management for BOB.

Handles loading and managing configuration from ~/.bob/config.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# Default configuration
DEFAULT_CONFIG = {
    "models": {
        "default": "claude-sonnet-4-5-20250929",
        "escalation": "claude-opus-4-5-20251101",
        # Set to true to use Opus for all tasks from the start
        "use_opus_default": False,
        # Enable extended thinking for complex tasks
        "enable_thinking": False,
        # Thinking budget tokens (when thinking is enabled)
        "thinking_budget": 10000,
    },
    "api": {
        "anthropic_api_key": "${ANTHROPIC_API_KEY}",
    },
    "database": {
        "type": "sqlite",
        "path": "~/.bob/bob.db",
    },
    "logging": {
        "level": "INFO",
        "format": "json",
    },
    "limits": {
        "max_cost_per_project": 100.0,
        "max_cost_per_session": 5.0,
        "warn_at_percent": 80,
    },
    "escalation": {
        "max_attempts_per_model": 3,
        "models": {
            "tier1": "claude-sonnet-4-5-20250929",
            "tier2": "claude-opus-4-5-20251101",
        },
    },
}


class ConfigManager:
    """
    Manages global BOB configuration.

    Configuration is stored in ~/.bob/config.yaml
    Environment variables in values like ${VAR_NAME} are expanded.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """
        Initialize config manager.

        Args:
            config_path: Path to config file (default: ~/.bob/config.yaml)
        """
        if config_path is None:
            config_path = Path.home() / ".bob" / "config.yaml"

        self.config_path = Path(config_path)
        self._config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns default config if file doesn't exist.
        Expands environment variables in string values.

        Returns:
            Configuration dictionary
        """
        if not self.config_path.exists():
            return self._expand_env_vars(DEFAULT_CONFIG.copy())

        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            # Merge with defaults (in case config file is incomplete)
            merged = self._merge_configs(DEFAULT_CONFIG.copy(), config)
            return self._expand_env_vars(merged)

        except Exception as e:
            # On error, return defaults
            print(f"Warning: Failed to load config from {self.config_path}: {e}")
            return DEFAULT_CONFIG.copy()

    def save(self, config: Dict[str, Any]) -> None:
        """
        Save configuration to file.

        Args:
            config: Configuration dictionary to save
        """
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Config key in dot notation (e.g., 'models.default')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if self._config is None:
            self._config = self.load()

        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.

        Args:
            key: Config key in dot notation (e.g., 'models.default')
            value: Value to set
        """
        if self._config is None:
            self._config = self.load()

        keys = key.split('.')
        config = self._config

        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        # Set the value
        config[keys[-1]] = value

    def get_all(self) -> Dict[str, Any]:
        """
        Get entire configuration.

        Returns:
            Complete configuration dictionary
        """
        if self._config is None:
            self._config = self.load()
        return self._config.copy()

    def reload(self) -> Dict[str, Any]:
        """
        Reload configuration from file.

        Returns:
            Reloaded configuration dictionary
        """
        self._config = None
        return self.load()

    @staticmethod
    def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two configuration dictionaries.

        Args:
            base: Base configuration
            override: Override configuration

        Returns:
            Merged configuration
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigManager._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    @staticmethod
    def _expand_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively expand environment variables in config values.

        Supports ${VAR_NAME} syntax.

        Args:
            config: Configuration dictionary

        Returns:
            Configuration with expanded environment variables
        """
        result = {}

        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = ConfigManager._expand_env_vars(value)
            elif isinstance(value, str) and "${" in value:
                # Expand environment variable
                result[key] = os.path.expandvars(value)
            else:
                result[key] = value

        return result

    def config_exists(self) -> bool:
        """
        Check if config file exists.

        Returns:
            True if config file exists, False otherwise
        """
        return self.config_path.exists()

    def create_default_config(self) -> None:
        """Create default config file if it doesn't exist."""
        if not self.config_exists():
            self.save(DEFAULT_CONFIG)


def get_config_manager(config_path: Optional[Path] = None) -> ConfigManager:
    """
    Factory function to get a ConfigManager instance.

    Args:
        config_path: Optional custom config path

    Returns:
        ConfigManager instance
    """
    return ConfigManager(config_path=config_path)


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from file.

    Args:
        config_path: Optional custom config path

    Returns:
        Configuration dictionary
    """
    manager = get_config_manager(config_path)
    return manager.load()
