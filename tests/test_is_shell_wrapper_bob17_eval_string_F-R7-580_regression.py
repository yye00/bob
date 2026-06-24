"""Regression test: F-R7-580 — shell wrapper detection for bash eval strings.

Acceptance criterion:
    pytest: tests/test_is_shell_wrapper_bob17_eval_string_F-R7-580_regression.py
    asserts is_shell_wrapper('/bin/bash -c eval timeout 5 /home/.../bob17 run --all')
    is True
"""

from __future__ import annotations

import pytest

from bob.orchestrator.probe_ancestry import is_shell_wrapper


def test_bash_with_eval_bob17_run_is_shell_wrapper():
    """F-R7-580 regression: bash -c eval ... bob17 run is a shell wrapper."""
    cmdline = "/bin/bash -c eval timeout 5 /home/yelkhamr/dark-factory/bob17/.venv/bin/bob17 run --all"
    assert is_shell_wrapper(cmdline) is True


def test_bare_bash_is_shell_wrapper():
    """/bin/bash alone is a shell wrapper."""
    assert is_shell_wrapper("/bin/bash") is True


def test_sh_is_shell_wrapper():
    """/bin/sh is a shell wrapper."""
    assert is_shell_wrapper("/bin/sh") is True


def test_dash_is_shell_wrapper():
    """dash is a shell wrapper."""
    assert is_shell_wrapper("dash") is True


def test_zsh_is_shell_wrapper():
    """zsh is a shell wrapper."""
    assert is_shell_wrapper("/usr/bin/zsh") is True


def test_ksh_is_shell_wrapper():
    """ksh is a shell wrapper."""
    assert is_shell_wrapper("ksh") is True


def test_fish_is_shell_wrapper():
    """fish is a shell wrapper."""
    assert is_shell_wrapper("/usr/local/bin/fish") is True


def test_timeout_prefix_is_shell_wrapper():
    """timeout command is treated as a wrapper."""
    assert is_shell_wrapper("timeout 5 bob17 run --all") is True


def test_full_path_timeout_is_shell_wrapper():
    """/usr/bin/timeout is a wrapper."""
    assert is_shell_wrapper("/usr/bin/timeout 30 bob22 run") is True


def test_empty_cmdline_returns_false():
    """Empty cmdline returns False (not a shell wrapper)."""
    assert is_shell_wrapper("") is False


def test_single_token_bash_returns_true():
    """Single-token '/bin/bash' returns True."""
    assert is_shell_wrapper("/bin/bash") is True


def test_quoted_arg_cmdline_returns_true():
    """bash -c 'bob17 run' returns True (bash is the argv[0])."""
    assert is_shell_wrapper("bash -c 'bob17 run'") is True


def test_python3_bob_run_is_not_shell_wrapper():
    """python3 /path/bobN run is not a shell wrapper."""
    assert is_shell_wrapper("python3 /opt/dark-factory/bob17/.venv/bin/bob17 run") is False


def test_bob17_directly_is_not_shell_wrapper():
    """/path/to/bob17 run is not a shell wrapper."""
    assert is_shell_wrapper("/home/yelkhamr/dark-factory/bob17/.venv/bin/bob17 run --all") is False


def test_bare_bob42_is_not_shell_wrapper():
    """bob42 run --all is not a shell wrapper."""
    assert is_shell_wrapper("bob42 run --all") is False
