"""Test-implementation coupling detector — canonical public module (feature 884b9e46).

Re-exports the full public API from :mod:`bob.test_coupling_detector` under
the canonical acceptance-criteria name ``test_implementation_coupling_detector``.

Public API
----------
- ``detect_internal_imports(workspace)`` → list[CouplingFinding]
- ``detect_shared_helpers(workspace)`` → list[CouplingFinding]
- ``detect_identical_constants(workspace)`` → list[CouplingFinding]
- ``check_test_impl_coupling(workspace)`` → CouplingResult
"""

from bob.test_coupling_detector import (  # noqa: F401
    CouplingFinding,
    CouplingResult,
    check_test_impl_coupling,
    detect_identical_constants,
    detect_internal_imports,
    detect_shared_helpers,
)

__all__ = [
    "CouplingFinding",
    "CouplingResult",
    "check_test_impl_coupling",
    "detect_identical_constants",
    "detect_internal_imports",
    "detect_shared_helpers",
]
