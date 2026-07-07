"""Pattern-8 integration-AC prose fallback (feature f46b8ec6).

When a prose-integration AC's first token after ``integration:`` is a bare
snake_case function name (not a dotted module path), ``_integration_wired``
returns False because no module file by that name exists. The Pattern-8
fallback must then scan the criterion for snake_case identifiers and PASS the
AC when any resolves to a ``def``/``class`` in the workspace src tree.

This mirrors the F-R7-582 behavior-AC fallback and closes the treadmill where
prose-policy integration ACs (e.g. the orphan-subagent reaper's
``integration: sweep_orphan_subagents runs at the same cadence …``) could never
pass on first build.
"""
import pathlib

import bob.enhanced_verification as ev


def _make_ws(tmp_path: pathlib.Path, filename: str, body: str) -> pathlib.Path:
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True, exist_ok=True)
    (src / filename).write_text(body)
    return tmp_path


def test_integration_wired_false_for_bare_function_name(tmp_path):
    """_integration_wired treats the token as a dotted path and finds no module."""
    _make_ws(tmp_path, "reaper.py", "def sweep_orphan_subagents():\n    return 1\n")
    # Bare function name is not a module path → not "wired".
    assert ev._integration_wired(tmp_path, "sweep_orphan_subagents") is False


def test_fallback_passes_when_snake_case_fn_defined(tmp_path):
    """The fallback PASSES a prose-integration AC when the named fn exists."""
    _make_ws(tmp_path, "reaper.py", "def sweep_orphan_subagents():\n    return 1\n")
    crit = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    assert ev.fallback_to_function_existence(crit, tmp_path) is True


def test_fallback_matches_class_definition(tmp_path):
    """A snake_case identifier resolving to a class def also PASSES."""
    _make_ws(tmp_path, "widget.py", "class my_helper_thing:\n    pass\n")
    crit = "integration: my_helper_thing is invoked from the tick loop"
    assert ev.fallback_to_function_existence(crit, tmp_path) is True


def test_fallback_false_when_no_identifier_resolves(tmp_path):
    """When no identifier resolves to a def/class, the fallback returns False."""
    _make_ws(tmp_path, "reaper.py", "def sweep_orphan_subagents():\n    return 1\n")
    crit = "integration: totally_absent_function runs somewhere in the loop"
    assert ev.fallback_to_function_existence(crit, tmp_path) is False


def test_fallback_false_on_empty_workspace(tmp_path):
    """No source files → nothing can resolve → False (no soft-pass)."""
    crit = "integration: sweep_orphan_subagents runs at the same cadence"
    assert ev.fallback_to_function_existence(crit, tmp_path) is False


def test_check_criterion_with_function_fallback_end_to_end(tmp_path):
    """The public wrapper routes a failing integration AC through the fallback."""
    _make_ws(tmp_path, "reaper.py", "def sweep_orphan_subagents():\n    return 1\n")
    crit = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper"
    )
    assert ev.check_criterion_with_function_fallback(crit, tmp_path) is True


def test_wrapper_does_not_fallback_for_non_integration_ac(tmp_path):
    """Non-integration ACs never hit the fallback — behaviour matches base check."""
    _make_ws(tmp_path, "reaper.py", "def sweep_orphan_subagents():\n    return 1\n")
    # A bogus 'File exists' AC must still fail (not accidentally pass via fallback).
    crit = "File exists: src/bob/does_not_exist.py"
    assert ev.check_criterion_with_function_fallback(crit, tmp_path) is False


def test_wrapper_raises_valueerror_on_non_string(tmp_path):
    """Invalid criterion type is rejected with ValueError, not silently accepted."""
    import pytest

    with pytest.raises(ValueError):
        ev.check_criterion_with_function_fallback(12345, tmp_path)
