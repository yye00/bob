"""bob3.watchdog — watchdog utilities for chain stall detection and escalation."""

from bob3.watchdog.stall_escalation import (
    escalate_spec_gate_stall,
    escalate_stall_observation,
    write_stall_attention_marker,
)

# Canonical alias: escalate_stall_to_attention is the needs_human_attention sentinel entry-point
escalate_stall_to_attention = escalate_stall_observation

__all__ = [
    "escalate_spec_gate_stall",
    "escalate_stall_observation",
    "escalate_stall_to_attention",
    "write_stall_attention_marker",
]
