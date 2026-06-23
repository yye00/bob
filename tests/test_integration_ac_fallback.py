"""Tests for bob3.integration_ac_fallback.resolve_integration_target.

Verifies the two-phase Pattern-8 integration AC resolution:
  1. Dotted-path resolution via _integration_wired.
  2. Function-existence fallback for bare snake_case identifiers.

Root cause: feature 85790dc6 (orphan-subagent reaper) NH'd because
'integration: sweep_orphan_subagents ...' was not recognized as a prose
AC — the first token is a bare function name, not a dotted module path.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.integration_ac_fallback import resolve_integration_target


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_src(workspace: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = workspace / "src" / "bob3" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# primary case: bare snake_case function name triggers fallback
# ---------------------------------------------------------------------------


def test_bare_function_in_prose_ac_passes_via_fallback(tmp_path: pathlib.Path) -> None:
    """Exact bug-report AC resolves when function exists in workspace."""
    _write_src(tmp_path, "orphan_reaper.py", """
        def sweep_orphan_subagents(db_path):
            pass
    """)
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    assert resolve_integration_target(criterion, tmp_path) is True


def test_bare_function_not_in_workspace_returns_false(tmp_path: pathlib.Path) -> None:
    """If the bare function doesn't exist in workspace, returns False."""
    criterion = "integration: nonexistent_func_abc runs every 60 seconds"
    assert resolve_integration_target(criterion, tmp_path) is False


# ---------------------------------------------------------------------------
# Phase 1: dotted module path resolution
# ---------------------------------------------------------------------------


def test_dotted_module_path_resolves(tmp_path: pathlib.Path) -> None:
    """Dotted module path that exists and is imported resolves in Phase 1."""
    _write_src(tmp_path, "orchestrator/run_loop.py", """
        def main():
            pass
    """)
    importer = tmp_path / "src" / "bob3" / "main.py"
    importer.write_text("from bob3.orchestrator.run_loop import main\n")

    criterion = "integration: bob3.orchestrator.run_loop"
    assert resolve_integration_target(criterion, tmp_path) is True


def test_dotted_module_not_imported_returns_false(tmp_path: pathlib.Path) -> None:
    """Dotted module that exists but is not imported returns False from Phase 1."""
    _write_src(tmp_path, "some_module.py", """
        def some_func():
            pass
    """)
    # No importer — _integration_wired returns False, fallback finds no snake_case func
    criterion = "integration: bob3.some_module"
    # No snake_case identifiers that match defs, so should return False
    assert resolve_integration_target(criterion, tmp_path) is False


# ---------------------------------------------------------------------------
# Phase 2: class definitions also satisfy fallback
# ---------------------------------------------------------------------------


def test_class_in_workspace_satisfies_fallback(tmp_path: pathlib.Path) -> None:
    """Class definitions resolve via function-existence fallback."""
    _write_src(tmp_path, "workers.py", """
        class orphan_worker_pool:
            pass
    """)
    criterion = "integration: orphan_worker_pool must be initialized before dispatch"
    assert resolve_integration_target(criterion, tmp_path) is True


# ---------------------------------------------------------------------------
# non-integration criterion
# ---------------------------------------------------------------------------


def test_non_integration_criterion_returns_false(tmp_path: pathlib.Path) -> None:
    """Criterion without 'integration:' prefix returns False."""
    criterion = "pytest: tests/test_something.py::test_foo"
    assert resolve_integration_target(criterion, tmp_path) is False


def test_file_exists_criterion_returns_false(tmp_path: pathlib.Path) -> None:
    """File-exists AC is not an integration AC — returns False."""
    criterion = "File exists: src/bob3/foo.py"
    assert resolve_integration_target(criterion, tmp_path) is False


# ---------------------------------------------------------------------------
# bad dotted path falls through to function-existence fallback
# ---------------------------------------------------------------------------


def test_bad_dotted_path_falls_through_to_function_existence(tmp_path: pathlib.Path) -> None:
    """Dotted path that doesn't resolve triggers fallback to function-existence."""
    _write_src(tmp_path, "watchdog.py", """
        def periodic_sweep():
            pass
    """)
    criterion = "integration: bob3.nonexistent periodic_sweep runs every 60s"
    assert resolve_integration_target(criterion, tmp_path) is True


# ---------------------------------------------------------------------------
# multiple identifiers: first match wins
# ---------------------------------------------------------------------------


def test_multiple_identifiers_first_match_wins(tmp_path: pathlib.Path) -> None:
    """Multiple snake_case identifiers: first existing one returns True."""
    _write_src(tmp_path, "reaper.py", """
        def stuck_executing_reaper():
            pass
    """)
    criterion = (
        "integration: sweep_orphan_subagents and stuck_executing_reaper are "
        "both idempotent watchdog tasks"
    )
    assert resolve_integration_target(criterion, tmp_path) is True


# ---------------------------------------------------------------------------
# importability / module-level checks
# ---------------------------------------------------------------------------


def test_module_importable() -> None:
    """Module bob3.integration_ac_fallback is importable."""
    import importlib
    mod = importlib.import_module("bob3.integration_ac_fallback")
    assert mod is not None


def test_resolve_integration_target_is_callable() -> None:
    """resolve_integration_target is callable and exported."""
    assert callable(resolve_integration_target)


def test_in_all_exports() -> None:
    """resolve_integration_target is in __all__."""
    from bob3 import integration_ac_fallback
    assert "resolve_integration_target" in integration_ac_fallback.__all__


# ---------------------------------------------------------------------------
# invalid inputs raise ValueError
# ---------------------------------------------------------------------------


def test_non_string_criterion_raises_value_error(tmp_path: pathlib.Path) -> None:
    """Non-string criterion raises ValueError."""
    with pytest.raises(ValueError, match="criterion must be a str"):
        resolve_integration_target(None, tmp_path)  # type: ignore[arg-type]


def test_non_path_workspace_raises_value_error() -> None:
    """Non-Path workspace raises ValueError."""
    with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
        resolve_integration_target("integration: foo_bar", "/some/path")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# empty criterion edge case
# ---------------------------------------------------------------------------


def test_empty_criterion_returns_false(tmp_path: pathlib.Path) -> None:
    """Empty string criterion returns False."""
    assert resolve_integration_target("", tmp_path) is False


def test_integration_prefix_only_returns_false(tmp_path: pathlib.Path) -> None:
    """Criterion that is just 'integration:' with no body returns False."""
    assert resolve_integration_target("integration:", tmp_path) is False
