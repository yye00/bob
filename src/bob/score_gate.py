"""bob.score_gate — public façade for the spec-quality score-gate loop.

Exposes :func:`score_gate_loop` as a stable import target at
``bob.score_gate.score_gate_loop``.  The implementation lives in
:mod:`bob.spec_synthesizer`; this module re-exports it with the canonical
name required by the acceptance criteria.
"""

from __future__ import annotations

from bob.spec_synthesizer import score_gate_loop  # noqa: F401

__all__ = ["score_gate_loop"]
