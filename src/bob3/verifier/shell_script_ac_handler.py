"""Pattern 9 — shell-script integration AC handler (F-R7-594).

Public entry point: handle_shell_script_ac

When an AC line starts with 'integration:' and the body resolves to an
existing, executable .sh or .bash file, demote the AC to PASS with a WARNING
log line tagged 'F-R7-594'.

Safety: missing or non-executable scripts return (False, reason) so real
bugs still surface. Non-script integration ACs return None and fall through
to the next pattern (regression guard).
"""

from __future__ import annotations

from bob3.verifier.shell_script_ac import handle_shell_script_ac  # noqa: F401

__all__ = ["handle_shell_script_ac"]
