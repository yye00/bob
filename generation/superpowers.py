"""Generation-level superpowers — re-exports bob3.superpowers for generation scripts.

This module exists so that bootstrap and generation-level scripts can import
superpowers utilities without resolving the full ``src/bob3/`` package path.
All functionality is delegated to ``bob3.superpowers``.

Feature: f3fd13df-ee18-49a0-8435-d329ffeebe7a
AC: File exists: generation/superpowers.py
"""

from __future__ import annotations

# Re-export the full public surface of bob3.superpowers so generation scripts
# that do `from generation.superpowers import X` continue to work.
from bob3.superpowers import (  # noqa: F401
    forbid_pytest_stdout_redirection,
    verify_pytest_no_stdout_redirection,
    verify_subagent_pytest_rules,
    verification_prompt_forbids_stdout_redirect,
    get_verification_prompt,
    get_tdd_prompt,
    should_use_tdd,
    get_feature_test_files,
    get_feature_test_paths,
    extract_pytest_paths,
    get_scoped_pytest_command,
    build_scoped_pytest_invocation,
    get_subagent_prompt,
    should_use_subagents,
    get_superpowers_orientation,
    build_superpowers_prompt,
    run_verification_checklist,
    reload_prompt_sources,
    reload_prompt_source_if_changed,
)
