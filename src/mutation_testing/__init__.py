"""mutation_testing — top-level module exposing verify_mutation_score.

AC: Function defined: mutation_testing.verify_mutation_score

This module re-exports ``verify_mutation_score`` from
``bob.mutmut_verifier`` so the function is accessible as
``mutation_testing.verify_mutation_score``.
"""

from bob.mutmut_verifier import (
    MUTATION_SCORE_THRESHOLD,
    MutationReport,
    MutmutMissingError,
    default_threshold,
    mutation_operators,
    never_mutates_failing_impl,
    passes_gate,
    persist_surviving_mutants,
    run_mutation_test,
    runs_only_after_pytest_pass,
    verify_mutation_score,
)

__all__ = [
    "verify_mutation_score",
    "MUTATION_SCORE_THRESHOLD",
    "MutationReport",
    "MutmutMissingError",
    "default_threshold",
    "mutation_operators",
    "never_mutates_failing_impl",
    "passes_gate",
    "persist_surviving_mutants",
    "run_mutation_test",
    "runs_only_after_pytest_pass",
]
