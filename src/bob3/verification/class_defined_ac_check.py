"""Handler for 'Class defined:' acceptance criteria.

Symmetric to the 'Function defined:' handler in enhanced_verification.py.
Extracts the class name from a dotted path criterion and searches the
workspace source tree for a matching class definition.

Public API
----------
extract_class_name_from_criterion(criterion) -> str | None
    Returns the class name (last component of dotted path) from a
    'Class defined: pkg.mod.ClassName' criterion string, or None if
    the criterion does not match the expected prefix.

check_class_defined_ac(class_name, workspace) -> bool
    Returns True when a 'class <name>:' or 'class <name>(...):'
    definition exists anywhere in the workspace Python source tree.
    Decorator lines above the class definition are irrelevant — only
    the 'class Name' token matters (handles @dataclass, pydantic,
    abstract base classes, etc.).
"""

from __future__ import annotations

import pathlib
import re

_CLASS_DEFINED_PREFIX_RE = re.compile(r"^class\s+defined:\s*(.+)$", re.IGNORECASE)


def extract_class_name_from_criterion(criterion: str) -> str | None:
    """Extract the class name from a 'Class defined: pkg.mod.ClassName' AC string.

    Returns the last dotted component (the class name), or None if the
    criterion does not start with 'Class defined:'.
    """
    m = _CLASS_DEFINED_PREFIX_RE.match(criterion.strip())
    if not m:
        return None
    dotted = m.group(1).strip()
    return dotted.rsplit(".", 1)[-1]


def check_class_defined_ac(class_name: str, workspace: pathlib.Path) -> bool:
    """Return True if 'class <class_name>' exists anywhere in workspace .py files.

    Matches both 'class Foo:' and 'class Foo(Base):' forms. A decorator
    above the class line (e.g. @dataclass, @pydantic.validator) is irrelevant
    — only the 'class Name' token is required to match.

    Exact name matching only: 'Report' does NOT match 'MutationReport'.
    """
    pattern = re.compile(rf"(?:^|\n)\s*class\s+{re.escape(class_name)}\s*[\(:]")

    try:
        for py_file in workspace.rglob("*.py"):
            if "build" in py_file.parts or ".git" in py_file.parts:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                if pattern.search(content):
                    return True
            except Exception:
                continue
    except Exception:
        return False

    return False
