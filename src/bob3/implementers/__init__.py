"""Bob3 implementer sub-agent utilities.

Implementer sub-agents should call ``refuse_start_unless_approved`` at
the top of their entry point to enforce the plan.yaml gate (F-R7-463).
"""

from bob3.orchestrator.plan_gate import (  # noqa: F401 — integration AC bcb6a22e
    refuse_implementer_when_unapproved as refuse_start_unless_approved,
)
