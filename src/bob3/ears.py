"""EARS (Easy Approach to Requirements Syntax) clause types and parser.

Re-exports the core EARS types and ``extract_ears_clauses`` from
:mod:`bob3.property_based_test_generator_hypothesis_ears` for use by
consumers that only need the EARS parsing layer without the Hypothesis
property-test runner.

Public API
----------
- :class:`EARSClauseKind`  — enum of EARS pattern families
- :class:`EARSClause`      — a single parsed EARS clause
- :func:`extract_ears_clauses` — parse clauses from free-form text
"""

from bob3.property_based_test_generator_hypothesis_ears import (
    EARSClause,
    EARSClauseKind,
    extract_ears_clauses,
)

__all__ = [
    "EARSClause",
    "EARSClauseKind",
    "extract_ears_clauses",
]
