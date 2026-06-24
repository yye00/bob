"""bob.mutation_tester — canonical entry point for the mutmut quality gate.

Wires mutmut 3.x as a verifier-stage quality gate. After pytest passes,
mutate the impl files and re-run the test suite. Rejects if
mutation_score < 0.75. Surviving mutants are persisted to
runs/<feature>/mutation_report.json; the next implementer attempt sees them
as "tests cannot distinguish your impl from these broken variants; strengthen
assertions."

Public API
----------
MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).

run_mutation_tests(feature_id, src_files, test_dir, workspace,
                   pytest_passed, *, threshold=None) -> dict | None
    Run the mutmut quality gate. Returns None when the gate is skipped
    (pytest failed or empty feature_id), a gate-result dict on success,
    or a dict with skipped=True when mutmut is unavailable.
"""

from __future__ import annotations

from bob.mutation_testing.mutmut_verifier import (
    MUTATION_SCORE_THRESHOLD,
    check_mutation_score,
    run_mutation_tests,
)

__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "check_mutation_score",
    "run_mutation_tests",
]
