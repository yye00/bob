"""bob77.verifier — integration of property-based AC verification into bob77.

Re-exports the verifier-facing API from ``bob.spec_quality.example_grammar``:

- ``emit_hypothesis_test`` — emits one Hypothesis test per :class:`PropertyAC`.
- ``emit_parametrize_test`` — emits one ``@pytest.mark.parametrize`` test per
  :class:`KeyExample` list, with seed=0.
- ``check_boundary_satisfied`` — checks whether boundary requirements are met.
- ``require_boundary_example`` — raises :class:`MissingBoundaryError` when
  boundary examples are absent from a numeric-range AC.

Usage in the verifier pipeline::

    from bob77.verifier import emit_hypothesis_test, emit_parametrize_test
    from bob77.ac_grammar import parse_property_ac, parse_key_example_ac

    prop = parse_property_ac("property: non_negative for st.integers() assert x >= 0")
    if prop:
        source = emit_hypothesis_test(prop, seed=0)

    examples = [parse_key_example_ac({"given": "0", "then": "0"})]
    source = emit_parametrize_test([e for e in examples if e], seed=0)
"""

from __future__ import annotations

import pathlib

from bob.spec_quality.example_grammar import (
    MissingBoundaryError,
    PropertyParseError,
    check_boundary_satisfied,
    emit_hypothesis_test,
    emit_parametrize_block,
    emit_parametrize_test,
    require_boundary_example,
)
from bob.verifier.shell_script_ac import handle_shell_script_ac as _handle_shell_script_ac


def pattern9_shell_script_handler(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 shell-script integration AC handler (F-R7-594).

    When an AC line starts with 'integration:' and the body is a path to an
    existing, executable .sh or .bash file, demote the AC to PASS with a WARNING.

    Returns:
        ``(True, "")`` — PASS-with-warning when script exists and is executable.
        ``(False, reason)`` — hard FAIL when script is missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; fall through.
    """
    return _handle_shell_script_ac(criterion, workspace)


__all__ = [
    "emit_hypothesis_test",
    "emit_parametrize_test",
    "emit_parametrize_block",
    "check_boundary_satisfied",
    "require_boundary_example",
    "MissingBoundaryError",
    "PropertyParseError",
    "pattern9_shell_script_handler",
]
