"""Tests for multi-target integration AC resolution.

Validates that extract_integration_targets returns all dotted-path candidates
from a multi-token body, and that resolve_integration_ac returns True when
either target is wired in the workspace.
"""
from __future__ import annotations

import pathlib

import pytest

from bob3.verification.integration_ac_resolver import (
    extract_integration_targets,
    resolve_integration_ac,
)

MULTI_TARGET_CRITERION = (
    "integration: bob3.x.y and bob3.a.b are both imported"
)


def test_extract_multi_target_finds_both() -> None:
    """extract_integration_targets must return at least ['bob3.x.y', 'bob3.a.b']."""
    targets = extract_integration_targets(MULTI_TARGET_CRITERION)
    assert "bob3.x.y" in targets, (
        f"Expected 'bob3.x.y' in extracted targets, got {targets!r}"
    )
    assert "bob3.a.b" in targets, (
        f"Expected 'bob3.a.b' in extracted targets, got {targets!r}"
    )


@pytest.fixture()
def workspace_with_bob3_x_y(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where bob3.x.y is wired (file exists + imported)."""
    src = tmp_path / "src"
    bob3_x = src / "bob3" / "x"
    bob3_x.mkdir(parents=True)
    (bob3_x / "y.py").write_text("def something(): pass\n")
    (src / "bob3" / "__init__.py").write_text("")
    (src / "bob3" / "x" / "__init__.py").write_text("")
    # Create a file that imports bob3.x.y
    importer = src / "bob3" / "consumer.py"
    importer.write_text("from bob3.x import y\n")
    return tmp_path


@pytest.fixture()
def workspace_with_bob3_a_b(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where bob3.a.b is wired (file exists + imported)."""
    src = tmp_path / "src"
    bob3_a = src / "bob3" / "a"
    bob3_a.mkdir(parents=True)
    (bob3_a / "b.py").write_text("def something(): pass\n")
    (src / "bob3" / "__init__.py").write_text("")
    (src / "bob3" / "a" / "__init__.py").write_text("")
    importer = src / "bob3" / "consumer.py"
    importer.write_text("from bob3.a import b\n")
    return tmp_path


@pytest.fixture()
def empty_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where neither bob3.x.y nor bob3.a.b exists."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "placeholder.py").write_text("# placeholder\n")
    return tmp_path


def test_resolve_true_when_first_target_wired(
    workspace_with_bob3_x_y: pathlib.Path,
) -> None:
    """resolve_integration_ac returns True if first dotted target is wired."""
    passed, reason = resolve_integration_ac(MULTI_TARGET_CRITERION, workspace_with_bob3_x_y)
    assert passed is True, (
        f"Expected True when bob3.x.y is wired; got passed={passed!r}, reason={reason!r}"
    )


def test_resolve_true_when_second_target_wired(
    workspace_with_bob3_a_b: pathlib.Path,
) -> None:
    """resolve_integration_ac returns True if second dotted target is wired."""
    passed, reason = resolve_integration_ac(MULTI_TARGET_CRITERION, workspace_with_bob3_a_b)
    assert passed is True, (
        f"Expected True when bob3.a.b is wired; got passed={passed!r}, reason={reason!r}"
    )


def test_resolve_demotes_when_neither_wired_but_prose(
    empty_workspace: pathlib.Path,
) -> None:
    """resolve_integration_ac demotes to warning when no target wired but body is prose."""
    passed, reason = resolve_integration_ac(MULTI_TARGET_CRITERION, empty_workspace)
    assert passed is True, (
        f"Expected True (prose demotion) when neither target wired; "
        f"got passed={passed!r}, reason={reason!r}"
    )
    assert "demoted" in reason.lower(), (
        f"Expected demotion reason, got: {reason!r}"
    )
