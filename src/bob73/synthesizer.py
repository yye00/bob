"""bob73.synthesizer — boundary + error-path AC coverage and object-format LLM parsing.

Re-exports the canonical implementation from bob_legacy.synthesizer so that both
`bob.synthesizer` and `bob73.synthesizer` resolve to the same functions.
"""
from __future__ import annotations

from bob_legacy.synthesizer import (
    inject_boundary_error_criteria,
    parse_criteria_response,
)

__all__ = [
    "inject_boundary_error_criteria",
    "parse_criteria_response",
]
