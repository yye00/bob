"""Gate-blocked feature re-synthesis facade for bob72.

Exposes ``re_synthesize_acceptance_criteria`` — the named entry point for
regenerating a gate-blocked feature's acceptance criteria until they clear the
spec-quality gate. Delegates to :mod:`bob.score_gate_loop`.
"""

from __future__ import annotations

from bob.score_gate_loop import re_synthesize_acceptance_criteria  # noqa: F401

__all__ = ["re_synthesize_acceptance_criteria"]
