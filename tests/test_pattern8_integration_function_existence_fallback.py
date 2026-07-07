"""Feature 969817ea: Pattern-8 integration AC handler MUST fall back to
function-existence when the first token after ``integration:`` is a bare
snake_case function name (not a dotted module path).

Root cause reproduced: an ``integration:`` AC whose body starts with a bare
function name (``sweep_orphan_subagents``) rather than a dotted module path.
``_integration_wired`` returns False for such names because no module file of
that name exists. The Pattern-8 handler must then fall back to scanning
snake_case identifiers for a matching ``def``/``class`` in the workspace src
tree and demote to PASS when one resolves.
"""
import pathlib

import pytest

import bob.enhanced_verification as ev


def _make_ws(tmp_path: pathlib.Path, func_name: str) -> pathlib.Path:
    """Create a workspace with src/pkg/mod.py defining ``func_name``."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text(f"def {func_name}():\n    return 1\n")
    return tmp_path


def test_bare_function_name_resolves_via_fallback(tmp_path):
    ws = _make_ws(tmp_path, "sweep_orphan_subagents")
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    assert ev.fallback_to_function_existence(criterion, ws) is True


def test_bare_function_name_missing_returns_false(tmp_path):
    # Workspace defines a different function; the AC names one that is absent.
    ws = _make_ws(tmp_path, "some_other_helper")
    criterion = (
        "integration: nonexistent_reaper_function runs at the same cadence as "
        "the existing reaper"
    )
    assert ev.fallback_to_function_existence(criterion, ws) is False


def test_integration_wired_false_for_bare_function_name(tmp_path):
    # _integration_wired treats its arg as a dotted module path; a bare
    # function name has no module file, so it must return False.
    ws = _make_ws(tmp_path, "sweep_orphan_subagents")
    assert ev._integration_wired(ws, "sweep_orphan_subagents") is False


def test_function_def_resolves(tmp_path):
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("def orphan_reaper():\n    return None\n")
    criterion = "integration: orphan_reaper is wired into the watchdog tick"
    assert ev.fallback_to_function_existence(criterion, tmp_path) is True


def test_check_criterion_returns_bool(tmp_path):
    ws = _make_ws(tmp_path, "sweep_orphan_subagents")
    result = ev._check_criterion(
        criterion="integration: sweep_orphan_subagents runs at the same cadence",
        workspace=ws,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert isinstance(result, bool)


def test_dotted_module_path_still_works():
    # The real bob.enhanced_verification module must satisfy a dotted-path AC.
    ws = pathlib.Path(__file__).resolve().parents[1]
    criterion = "integration: bob.enhanced_verification"
    assert ev.pattern_8_integration_wired(criterion, ws) is True


def test_non_integration_criterion_ignored(tmp_path):
    ws = _make_ws(tmp_path, "sweep_orphan_subagents")
    # A criterion that does not start with integration: must not be demoted.
    assert (
        ev.fallback_to_function_existence(
            "File exists: src/pkg/mod.py", ws
        )
        is False
    )
