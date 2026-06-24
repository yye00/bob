"""Tests for multi-target integration AC resolution.

Validates that extract_integration_targets returns all dotted-path candidates
from a multi-token body, and that resolve_integration_ac returns True when
either target is wired in the workspace.
"""
from __future__ import annotations

import pathlib

import pytest

from bob.verification.integration_ac_resolver import (
    extract_integration_targets,
    resolve_integration_ac,
)

MULTI_TARGET_CRITERION = (
    "integration: bob.x.y and bob.a.b are both imported"
)


def test_extract_multi_target_finds_both() -> None:
    """extract_integration_targets must return at least ['bob.x.y', 'bob.a.b']."""
    targets = extract_integration_targets(MULTI_TARGET_CRITERION)
    assert "bob.x.y" in targets, (
        f"Expected 'bob.x.y' in extracted targets, got {targets!r}"
    )
    assert "bob.a.b" in targets, (
        f"Expected 'bob.a.b' in extracted targets, got {targets!r}"
    )


@pytest.fixture()
def workspace_with_bob_x_y(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where bob.x.y is wired (file exists + imported)."""
    src = tmp_path / "src"
    bob_x = src / "bob" / "x"
    bob_x.mkdir(parents=True)
    (bob_x / "y.py").write_text("def something(): pass\n")
    (src / "bob" / "__init__.py").write_text("")
    (src / "bob" / "x" / "__init__.py").write_text("")
    # Create a file that imports bob.x.y
    importer = src / "bob" / "consumer.py"
    importer.write_text("from bob.x import y\n")
    return tmp_path


@pytest.fixture()
def workspace_with_bob_a_b(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where bob.a.b is wired (file exists + imported)."""
    src = tmp_path / "src"
    bob_a = src / "bob" / "a"
    bob_a.mkdir(parents=True)
    (bob_a / "b.py").write_text("def something(): pass\n")
    (src / "bob" / "__init__.py").write_text("")
    (src / "bob" / "a" / "__init__.py").write_text("")
    importer = src / "bob" / "consumer.py"
    importer.write_text("from bob.a import b\n")
    return tmp_path


@pytest.fixture()
def empty_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where neither bob.x.y nor bob.a.b exists."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "placeholder.py").write_text("# placeholder\n")
    return tmp_path


def test_resolve_true_when_first_target_wired(
    workspace_with_bob_x_y: pathlib.Path,
) -> None:
    """resolve_integration_ac returns True if first dotted target is wired."""
    passed, reason = resolve_integration_ac(MULTI_TARGET_CRITERION, workspace_with_bob_x_y)
    assert passed is True, (
        f"Expected True when bob.x.y is wired; got passed={passed!r}, reason={reason!r}"
    )


def test_resolve_true_when_second_target_wired(
    workspace_with_bob_a_b: pathlib.Path,
) -> None:
    """resolve_integration_ac returns True if second dotted target is wired."""
    passed, reason = resolve_integration_ac(MULTI_TARGET_CRITERION, workspace_with_bob_a_b)
    assert passed is True, (
        f"Expected True when bob.a.b is wired; got passed={passed!r}, reason={reason!r}"
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
