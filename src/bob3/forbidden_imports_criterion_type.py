"""forbidden_imports: criterion type for enhanced_verification.

This module provides the ``forbidden_imports:`` acceptance-criterion type,
which bans named top-level imports from appearing in source files under src/.

Uses AST parsing — string literals, comments, and variable names that happen
to contain a module name do not trigger a failure.

Criterion syntax
----------------
Plain comma-separated list::

    forbidden_imports: transformers, torch.autograd

YAML-style bracket list::

    forbidden_imports: [transformers, torch.autograd]

A module name ``m`` matches any of:

* ``import m``
* ``import m.something``   (prefix match)
* ``from m import ...``
* ``from m.something import ...``   (prefix match)

Files under ``tests/`` are excluded from the scan.

Public API
----------
:func:`check_forbidden_imports`
    Core checker; returns ``(passed, details)``.

:func:`parse_forbidden_imports_list`
    Parse the comma/bracket list syntax into a ``list[str]``.
"""

from __future__ import annotations

from bob3.enhanced_verification import (
    _parse_forbidden_imports_list as parse_forbidden_imports_list,
    check_forbidden_imports,
)

__all__ = [
    "check_forbidden_imports",
    "parse_forbidden_imports_list",
]
