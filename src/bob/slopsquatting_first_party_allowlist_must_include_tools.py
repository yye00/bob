"""Slopsquatting first-party allowlist — MUST include tools/ and project-root .py modules.

F-R7-481 forward-carry (hardened): the slopsquatting scanner's first-party
allowlist must walk ``tools/`` and project-root sibling ``.py`` files in
addition to ``src/<pkg>/``.

Background
----------
bob version 17, round 1 (2026-05-31 ~07:42Z): feature b20b4725
(zero-reported-cost budget enforcement) NH'd at attempt 5/5 with::

    slopsquatting/high: Imported package 'spec_quality_score'
    (distribution 'spec_quality_score') does not exist on PyPI.

Root cause: ``security_checks._read_first_party_packages(workspace)`` walked
only ``workspace/src/<pkg>/...`` for first-party allowlist.  But
``spec_quality_score.py`` lives at ``workspace/tools/spec_quality_score.py``
(a project-internal script), and sub-agents routinely ``import spec_quality_score``.
The slopsquatting probe queries PyPI, no such package exists → hard-fail.

This module exposes a public wrapper ``slopsquatting_first_party_allowlist_must_include_tools``
that builds the hardened allowlist for a given workspace path.
"""

from __future__ import annotations

from pathlib import Path


def slopsquatting_first_party_allowlist_must_include_tools(
    workspace: Path | str,
) -> set[str]:
    """Build the slopsquatting first-party allowlist for *workspace*.

    Collects module names from:
    - ``pyproject.toml`` ``[project].name``
    - ``src/`` top-level packages and their immediate ``.py`` children
    - ``tools/`` ``.py`` files and packages
    - project-root ``.py`` files

    Args:
        workspace: Path to the project root.  Must be an existing directory.

    Returns:
        A set of import-name strings that are known-first-party and must NOT
        be probed against PyPI.  Returns an empty set when *workspace* has no
        Python source tree (not an error — the project may be empty).

    Raises:
        ValueError: when *workspace* is ``None``, an empty string, or resolves
            to a path that is not an existing directory.
    """
    if workspace is None:
        raise ValueError("workspace must not be None")
    ws = Path(workspace)
    if str(workspace) == "":
        raise ValueError("workspace must not be an empty string")
    if not ws.exists():
        raise ValueError(f"workspace does not exist: {ws}")
    if not ws.is_dir():
        raise ValueError(f"workspace must be a directory, got: {ws}")

    pkgs: set[str] = set()

    # pyproject.toml project name
    pyproj = ws / "pyproject.toml"
    if pyproj.exists():
        try:
            import tomllib
            data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
            project = data.get("project", {})
            if name := project.get("name"):
                pkgs.add(str(name).replace("-", "_"))
        except Exception:  # noqa: BLE001
            pass

    # src/ tree
    src = ws / "src"
    if src.is_dir():
        for child in src.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                pkgs.add(child.name)
                for grand in child.iterdir():
                    if grand.is_dir() and (grand / "__init__.py").exists():
                        pkgs.add(grand.name)
                    elif grand.is_file() and grand.suffix == ".py" and grand.stem != "__init__":
                        pkgs.add(grand.stem)
            elif child.is_file() and child.suffix == ".py" and child.stem != "__init__":
                pkgs.add(child.stem)

    # tools/ tree — project scripts importable as first-party modules
    tools_dir = ws / "tools"
    if tools_dir.is_dir():
        for child in tools_dir.iterdir():
            if child.is_file() and child.suffix == ".py" and child.stem != "__init__":
                pkgs.add(child.stem)
            elif child.is_dir() and (child / "__init__.py").exists():
                pkgs.add(child.name)

    # project-root .py siblings
    for child in ws.iterdir():
        if child.is_file() and child.suffix == ".py" and child.stem != "__init__":
            pkgs.add(child.stem)

    return pkgs
