"""weekend_watchdog — convergence detection for bob.

Provides check_convergence, the Python equivalent of the shell
check_convergence function in tools/weekend_watchdog.sh.  Both compare
completed feature sets across generations by spec_slot (stable YAML key)
rather than by UUID (minted fresh on every `bob init`).

Also re-exports stall escalation utilities so callers can escalate
repeated spec_gate_stall_observed events to a needs_human_attention
sentinel without importing bob.stall_escalation directly.
"""

from __future__ import annotations

import pathlib
from typing import Union

from bob.convergence_detector import check_convergence  # noqa: F401 — re-exported
from bob.stall_escalation import (  # noqa: F401 — integration re-export
    escalate_stall_observation,
    write_stall_attention_marker,
)

__all__ = ["check_convergence", "escalate_stall_observation", "write_stall_attention_marker"]
