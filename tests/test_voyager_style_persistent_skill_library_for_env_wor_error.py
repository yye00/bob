"""Error path tests for the Voyager-style persistent skill library.

AC: pytest: tests/test_voyager_style_persistent_skill_library_for_env_wor_error.py
    — invalid input raises ValueError and the function does not silently succeed.
"""

import pathlib
import pytest

from bob73.skill_library import write_skill
from bob73.preflight import search_skill_library
from bob.skill_library.registry import (
    apply_skill,
    search_skills,
    SkillHit,
)


VALID_SHIM = '"""Valid shim."""\ndef apply(context): return "ok"\n'


# ---------------------------------------------------------------------------
# Error path: write_skill with invalid inputs
# ---------------------------------------------------------------------------


def test_write_skill_empty_description_raises(tmp_path):
    """write_skill with empty capability_description raises ValueError."""
    with pytest.raises(ValueError):
        write_skill(
            capability_description="",
            shim_module_src=VALID_SHIM,
            workspace=tmp_path,
        )


def test_write_skill_whitespace_description_raises(tmp_path):
    """write_skill with whitespace-only description raises ValueError."""
    with pytest.raises(ValueError):
        write_skill(
            capability_description="   \t\n  ",
            shim_module_src=VALID_SHIM,
            workspace=tmp_path,
        )


def test_write_skill_empty_shim_src_raises(tmp_path):
    """write_skill with empty shim_module_src raises ValueError."""
    with pytest.raises(ValueError):
        write_skill(
            capability_description="some valid capability",
            shim_module_src="",
            workspace=tmp_path,
        )


def test_write_skill_whitespace_shim_src_raises(tmp_path):
    """write_skill with whitespace-only shim_module_src raises ValueError."""
    with pytest.raises(ValueError):
        write_skill(
            capability_description="some valid capability",
            shim_module_src="   \n\t  ",
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Error path: search_skill_library with invalid inputs
# ---------------------------------------------------------------------------


def test_search_skill_library_empty_query_raises():
    """search_skill_library with empty string raises ValueError."""
    with pytest.raises(ValueError):
        search_skill_library(capability_query="")


def test_search_skill_library_whitespace_query_raises():
    """search_skill_library with whitespace-only query raises ValueError."""
    with pytest.raises(ValueError):
        search_skill_library(capability_query="   \t  ")


def test_search_skill_library_none_query_raises():
    """search_skill_library with None raises ValueError (type error)."""
    with pytest.raises((ValueError, TypeError)):
        search_skill_library(capability_query=None)


def test_search_skill_library_integer_query_raises():
    """search_skill_library with non-string query raises ValueError."""
    with pytest.raises(ValueError):
        search_skill_library(capability_query=42)


# ---------------------------------------------------------------------------
# Error path: apply_skill with broken shim
# ---------------------------------------------------------------------------


def test_apply_skill_syntax_error_shim_returns_failure():
    """apply_skill with a shim that has a syntax error returns success=False."""
    bad_shim = SkillHit(
        skill_id="bad_skill",
        capability_description="broken",
        similarity=1.0,
        shim_module_src="def apply(context: !!invalid syntax",
    )
    result = apply_skill(bad_shim, context={})
    assert result.success is False
    assert result.error is not None
    assert len(result.error) > 0


def test_apply_skill_missing_apply_function_returns_failure():
    """apply_skill with a shim that doesn't define apply() returns success=False."""
    no_apply_shim = SkillHit(
        skill_id="no_apply",
        capability_description="no apply function",
        similarity=1.0,
        shim_module_src='"""No apply defined."""\nx = 42\n',
    )
    result = apply_skill(no_apply_shim, context={})
    assert result.success is False
    assert "apply" in result.error.lower()


def test_apply_skill_raising_apply_function_returns_failure():
    """apply_skill with apply() that raises returns success=False not re-raises."""
    raising_shim = SkillHit(
        skill_id="raising_skill",
        capability_description="raising apply",
        similarity=1.0,
        shim_module_src='"""Raising shim."""\ndef apply(context): raise RuntimeError("boom")\n',
    )
    result = apply_skill(raising_shim, context={})
    assert result.success is False
    assert "boom" in result.error


# ---------------------------------------------------------------------------
# Error path: does NOT silently succeed on invalid input
# ---------------------------------------------------------------------------


def test_write_skill_does_not_silently_succeed_on_empty_desc(tmp_path):
    """write_skill with empty description must raise; no file is created silently."""
    with pytest.raises(ValueError):
        write_skill(
            capability_description="",
            shim_module_src=VALID_SHIM,
            workspace=tmp_path,
        )
    skill_lib = tmp_path / "skill_library"
    # Either no directory or no shim files
    if skill_lib.exists():
        shim_files = list(skill_lib.glob("skill_*.py"))
        assert shim_files == [], f"Silently created shim files: {shim_files}"


def test_search_skill_library_does_not_silently_succeed_on_empty_query():
    """search_skill_library with empty query must raise, not return a result."""
    with pytest.raises(ValueError):
        result = search_skill_library(capability_query="")
        # Should never reach here
        assert False, f"Expected ValueError but got: {result}"
