"""Example project-internal tool script.

Demonstrates that tools/ directory .py files are first-party modules
and must be included in the slopsquatting allowlist to avoid false-positive
PyPI probe failures.
"""

from __future__ import annotations


def foo() -> str:
    """Return a placeholder string for testing purposes."""
    return "foo"
