"""F-R7-478: classify_exit — marketplace ENOENT path is transient."""

import pytest
from bob3.orchestrator.spawn_retry import classify_exit


def test_enoent_claude_is_transient():
    result = classify_exit(
        exit_code=1,
        stderr="spawn ENOENT: No such file or directory, spawn /usr/local/bin/claude",
    )
    assert result == "transient"


def test_no_such_file_claude_is_transient():
    result = classify_exit(
        exit_code=1,
        stderr="Error: No such file or directory claude",
    )
    assert result == "transient"


def test_enoent_lowercase_is_transient():
    result = classify_exit(
        exit_code=1,
        stderr="spawn enoent: could not find claude in PATH",
    )
    assert result == "transient"


def test_marketplace_env_config_enoent():
    """Simulate the 2026-05-24 marketplace-path incident stderr."""
    stderr = (
        "Error: Command failed: claude --dangerously-skip-permissions\n"
        "spawn ENOENT: No such file or directory, spawn 'claude'\n"
        "at ChildProcess.<anonymous>"
    )
    result = classify_exit(exit_code=1, stderr=stderr)
    assert result == "transient"
