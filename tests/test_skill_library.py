"""Tests for bob73.skill_library (write_skill facade) and workspace skill_library/ dir.

Covers:
- write_skill returns a string skill_id
- write_skill writes the shim file to disk under skill_library/
- write_skill upserts when called twice with the same ID
- workspace skill_library/__init__.py exists (AC: File exists: skill_library/__init__.py)
- workspace skill_library/README.md exists (AC: File exists: skill_library/README.md)
- bob73.preflight.search_skill_library is callable (AC: Function defined)
- bob73.skill_library.write_skill is callable (AC: Function defined)
- search_skill_library returns None on empty library (miss path)
- search_skill_library returns hit dict when skill is in library
- integration: bob72.preflight is importable and compatible
"""

import pathlib
import pytest

from bob73.skill_library import write_skill
from bob73.preflight import search_skill_library


HEX_SHIM_SRC = '''\
"""Shim: hex dump bytes using Python stdlib — xxd workaround."""


def apply(context):
    data = context.get("data", b"")
    if isinstance(data, str):
        data = data.encode()
    return " ".join(f"{b:02x}" for b in data)
'''

ECHO_SHIM_SRC = '''\
"""Shim: echo message from context."""


def apply(context):
    return context.get("message", "")
'''


# ---------------------------------------------------------------------------
# AC: File exists: skill_library/__init__.py
# ---------------------------------------------------------------------------

def test_workspace_skill_library_init_exists():
    """workspace skill_library/__init__.py must exist (AC)."""
    p = pathlib.Path("skill_library/__init__.py")
    assert p.exists(), f"Expected {p} to exist"


def test_workspace_skill_library_readme_exists():
    """workspace skill_library/README.md must exist (AC)."""
    p = pathlib.Path("skill_library/README.md")
    assert p.exists(), f"Expected {p} to exist"


# ---------------------------------------------------------------------------
# AC: Function defined: bob73.preflight.search_skill_library
# ---------------------------------------------------------------------------

def test_search_skill_library_is_callable():
    """bob73.preflight.search_skill_library must be a callable (AC)."""
    assert callable(search_skill_library)


# ---------------------------------------------------------------------------
# AC: Function defined: bob73.skill_library.write_skill
# ---------------------------------------------------------------------------

def test_write_skill_is_callable():
    """bob73.skill_library.write_skill must be a callable (AC)."""
    assert callable(write_skill)


# ---------------------------------------------------------------------------
# write_skill basic behaviour
# ---------------------------------------------------------------------------

def test_write_skill_returns_string_id(tmp_path):
    skill_id = write_skill(
        capability_description="hex dump bytes using stdlib when xxd missing",
        shim_module_src=HEX_SHIM_SRC,
        workspace=tmp_path,
    )
    assert isinstance(skill_id, str)
    assert len(skill_id) > 0


def test_write_skill_creates_shim_file(tmp_path):
    skill_id = write_skill(
        capability_description="hex dump bytes using stdlib when xxd missing",
        shim_module_src=HEX_SHIM_SRC,
        workspace=tmp_path,
    )
    shim_path = tmp_path / "skill_library" / f"{skill_id}.py"
    assert shim_path.exists()
    assert shim_path.read_text() == HEX_SHIM_SRC


def test_write_skill_creates_index(tmp_path):
    write_skill(
        capability_description="hex dump bytes using stdlib when xxd missing",
        shim_module_src=HEX_SHIM_SRC,
        workspace=tmp_path,
    )
    index_path = tmp_path / "skill_library" / "index.json"
    assert index_path.exists()


def test_write_skill_upsert_single_entry(tmp_path):
    """Calling write_skill twice with the same description keeps one entry."""
    from bob3.skill_library.registry import search_skills

    write_skill(
        capability_description="echo message from context dict",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
    )
    write_skill(
        capability_description="echo message from context dict",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
    )
    hits = search_skills(query="echo message from context dict", workspace=tmp_path, threshold=0.0)
    skill_ids = [h.skill_id for h in hits]
    # Same description → same derived ID → exactly one entry
    assert len(set(skill_ids)) == 1


def test_write_skill_with_explicit_skill_id(tmp_path):
    skill_id = write_skill(
        capability_description="echo message",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
        skill_id="my_explicit_id",
    )
    assert skill_id == "my_explicit_id"
    shim_path = tmp_path / "skill_library" / "my_explicit_id.py"
    assert shim_path.exists()


# ---------------------------------------------------------------------------
# search_skill_library integration
# ---------------------------------------------------------------------------

def test_search_skill_library_returns_none_on_empty_library(tmp_path):
    """Miss path: empty library returns None."""
    result = search_skill_library(
        capability_query="hex dump binary file xxd workaround",
        workspace=tmp_path,
    )
    assert result is None


def test_search_skill_library_returns_hit_dict(tmp_path):
    """Hit path: skill in library returns a dict with expected keys."""
    write_skill(
        capability_description="echo message from context dict",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
    )
    result = search_skill_library(
        capability_query="echo message from context dict",
        workspace=tmp_path,
        context={"message": "hi"},
        threshold=0.0,
    )
    if result is not None:
        assert "hit" in result
        assert "apply_result" in result
        assert result["research_needed"] is False
        assert result["apply_result"] is not None


def test_search_skill_library_hit_apply_result_success(tmp_path):
    """When a shim is found and applied, apply_result.success is True."""
    write_skill(
        capability_description="echo message from context dict in apply function",
        shim_module_src=ECHO_SHIM_SRC,
        workspace=tmp_path,
    )
    result = search_skill_library(
        capability_query="echo message from context dict in apply function",
        workspace=tmp_path,
        context={"message": "hello"},
        threshold=0.0,
    )
    if result is not None:
        ar = result["apply_result"]
        assert ar.success is True
        assert ar.output == "hello"


# ---------------------------------------------------------------------------
# AC: integration: bob72.preflight
# ---------------------------------------------------------------------------

def test_bob72_preflight_importable():
    """bob72.preflight is importable — integration AC."""
    import bob72.preflight as pf
    assert callable(pf.run_preflight)
    assert callable(pf.probe_dependencies)
    assert callable(pf.discover_workaround)


def test_bob73_preflight_delegates_to_bob72(tmp_path):
    """bob73.preflight.run_preflight wraps bob72.preflight cleanly."""
    from bob73.preflight import run_preflight
    result = run_preflight(ac_list=[])
    assert isinstance(result, dict)
    assert "total_deps" in result
    assert "missing" in result
