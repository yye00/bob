"""F-R7-478: load_patterns hot-reloads config/spawn_retry.yaml on each call."""

import re
import tempfile
from pathlib import Path

import pytest
import yaml

from bob.orchestrator.spawn_retry import classify_exit, load_patterns


def _write_config(tmp_dir: Path, patterns: list[str]) -> Path:
    cfg_path = tmp_dir / "spawn_retry.yaml"
    cfg_path.write_text(
        yaml.dump({"TRANSIENT_PATTERNS": patterns}),
        encoding="utf-8",
    )
    return cfg_path


def test_load_patterns_from_custom_config(tmp_path):
    """load_patterns uses the custom config when provided."""
    cfg = _write_config(tmp_path, ["MY_SPECIAL_TRANSIENT_MARKER"])
    patterns = load_patterns(cfg)
    assert any(p.search("MY_SPECIAL_TRANSIENT_MARKER") for p in patterns)


def test_hot_reload_picks_up_changes(tmp_path):
    """A second call to load_patterns sees updated YAML without restart."""
    cfg = _write_config(tmp_path, ["PATTERN_V1"])
    patterns_v1 = load_patterns(cfg)
    assert any(p.search("PATTERN_V1") for p in patterns_v1)
    assert not any(p.search("PATTERN_V2") for p in patterns_v1)

    # Overwrite with new patterns
    _write_config(tmp_path, ["PATTERN_V2"])
    patterns_v2 = load_patterns(cfg)
    assert any(p.search("PATTERN_V2") for p in patterns_v2)
    assert not any(p.search("PATTERN_V1") for p in patterns_v2)


def test_fallback_when_config_missing():
    """load_patterns falls back to defaults when config is absent."""
    patterns = load_patterns("/nonexistent/path/spawn_retry.yaml")
    assert len(patterns) > 0
    # Default patterns must handle ECONNRESET
    assert any(p.search("ECONNRESET") for p in patterns)


def test_classify_exit_uses_custom_pattern(tmp_path):
    """classify_exit respects the hot-reloaded config_path."""
    cfg = _write_config(tmp_path, ["VERY_CUSTOM_TRANSIENT"])
    result = classify_exit(
        exit_code=1,
        stderr="VERY_CUSTOM_TRANSIENT occurred in subprocess",
        config_path=cfg,
    )
    assert result == "transient"


def test_classify_exit_unknown_pattern_is_real_failure(tmp_path):
    """classify_exit with a custom config does not match unrelated stderr."""
    cfg = _write_config(tmp_path, ["VERY_CUSTOM_TRANSIENT"])
    result = classify_exit(
        exit_code=1,
        stderr="SyntaxError: invalid syntax",
        config_path=cfg,
    )
    assert result == "real_failure"
