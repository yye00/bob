"""Tests for Pattern-8 integration AC handler fallback to function-existence.

Verifies the canonical entry point
``bob3.pattern_8_integration_ac_handler_must_fall_back_function``
(function ``pattern_8_integration_ac_handler_must_fall_back_function``).

The key requirement (F-R7-583 / 6797d411): when the first token after
'integration:' is a bare snake_case function name (not a dotted module path),
Pattern 8 MUST fall back to function-existence scanning rather than hard-failing.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.pattern_8_integration_ac_handler_must_fall_back_function import (
    pattern_8_integration_ac_handler_must_fall_back_function,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_src_file(workspace: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    """Write a Python source file into workspace/src/bob3/."""
    p = workspace / "src" / "bob3" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# primary AC test (required by spec)
# ---------------------------------------------------------------------------


def test_pattern_8_integration_ac_handler_must_fall_back_function(
    tmp_path: pathlib.Path,
) -> None:
    """Primary AC test: bare-function prose-integration AC resolves via fallback.

    Mirrors the real bug: 'integration: sweep_orphan_subagents runs at the
    same cadence ...' should PASS when sweep_orphan_subagents is defined in
    the workspace, even though it's not a dotted module path.
    """
    _make_src_file(
        tmp_path,
        "orphan_reaper.py",
        """
        def sweep_orphan_subagents(db_path):
            pass
        """,
    )
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is True, (
        "Pattern 8 must fall back to function-existence when first token is a "
        "bare snake_case function name, not a dotted module path"
    )


# ---------------------------------------------------------------------------
# dotted module path still resolves (regression guard)
# ---------------------------------------------------------------------------


def test_dotted_module_path_passes(tmp_path: pathlib.Path) -> None:
    """Existing dotted-path behaviour is unaffected by the fallback."""
    # Create a module file that is imported elsewhere
    module_file = _make_src_file(
        tmp_path,
        "orchestrator/run_loop.py",
        """
        def main():
            pass
        """,
    )
    # Create an importer so _integration_wired returns True
    importer = tmp_path / "src" / "bob3" / "main.py"
    importer.write_text("from bob3.orchestrator.run_loop import main\n")

    criterion = "integration: bob3.orchestrator.run_loop"
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# bare function not found — pure single-token body, no prose connectors → False
# ---------------------------------------------------------------------------


def test_bare_function_not_in_workspace_returns_false(tmp_path: pathlib.Path) -> None:
    """Single-token body with no connectors and no matching def → False.

    'integration: nonexistent_func_xyz' has no spaces/connectors, so it is
    treated as a dotted-path attempt (fails) then falls through without
    matching any snake_case def in the workspace.
    """
    # No matching def in workspace and no prose connectors
    criterion = "integration: nonexistent_func_xyz"
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# non-integration criterion → False (no-op)
# ---------------------------------------------------------------------------


def test_non_integration_criterion_returns_false(tmp_path: pathlib.Path) -> None:
    """Non-integration ACs are not handled — function returns False."""
    criterion = "pytest: tests/test_something.py::test_foo"
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# class-defined identifier also satisfies fallback
# ---------------------------------------------------------------------------


def test_class_defined_satisfies_fallback(tmp_path: pathlib.Path) -> None:
    """A class definition in workspace also satisfies the function-existence fallback."""
    _make_src_file(
        tmp_path,
        "workers.py",
        """
        class orphan_worker_pool:
            pass
        """,
    )
    criterion = "integration: orphan_worker_pool must be initialized before dispatch"
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# multiple snake_case identifiers — first match wins
# ---------------------------------------------------------------------------


def test_multiple_identifiers_first_match_wins(tmp_path: pathlib.Path) -> None:
    """If the body has several snake_case names, the first one that exists passes."""
    _make_src_file(
        tmp_path,
        "reaper.py",
        """
        def stuck_executing_reaper():
            pass
        """,
    )
    criterion = (
        "integration: sweep_orphan_subagents and stuck_executing_reaper are "
        "both idempotent watchdog tasks"
    )
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# empty workspace with single-token body → False
# ---------------------------------------------------------------------------


def test_empty_workspace_returns_false(tmp_path: pathlib.Path) -> None:
    """With no source files and a single-token body, function-existence fallback returns False."""
    # Single-token, no connectors — not treated as prose demotion
    criterion = "integration: some_func_name_only"
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# dotted path that doesn't exist but body has valid snake_case → fallback True
# ---------------------------------------------------------------------------


def test_bad_dotted_path_falls_back_to_function_existence(tmp_path: pathlib.Path) -> None:
    """When a dotted token doesn't resolve, fallback scans snake_case identifiers."""
    _make_src_file(
        tmp_path,
        "watchdog.py",
        """
        def periodic_sweep():
            pass
        """,
    )
    # The dotted path 'bob3.nonexistent' won't resolve, but 'periodic_sweep' will.
    criterion = "integration: bob3.nonexistent periodic_sweep runs every 60s"
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# exact prose from the bug report (sweep_orphan_subagents AC body)
# ---------------------------------------------------------------------------


def test_exact_bug_report_ac_body(tmp_path: pathlib.Path) -> None:
    """Exact AC from the bug report (85790dc6 orphan-subagent reaper NH failure)."""
    _make_src_file(
        tmp_path,
        "mcp_lifecycle.py",
        """
        def sweep_orphan_subagents(db_path):
            \"\"\"Sweep orphan subagents.\"\"\"
            pass
        """,
    )
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    result = pattern_8_integration_ac_handler_must_fall_back_function(criterion, tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# callable is importable from the module
# ---------------------------------------------------------------------------


def test_function_is_importable() -> None:
    """The function is importable from the declared module."""
    from bob3.pattern_8_integration_ac_handler_must_fall_back_function import (
        pattern_8_integration_ac_handler_must_fall_back_function as fn,
    )
    assert callable(fn)
