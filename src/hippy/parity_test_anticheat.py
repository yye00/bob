"""hippy façade for parity-test anti-cheat AC synthesis (feature 7951f7fc).

A *parity* (a.k.a. equivalence) acceptance criterion checks an implementation's
output against a reference. Proving an op correct against a SINGLE frozen
expected value is gameable three ways by an attempt-pressured builder without
doing the real work:

  (a) return the baked-in constant the test checks;
  (b) compute on the host (numpy / pure Python) and disguise it behind a
      device-copy so it "looks" like the target substrate;
  (c) special-case the one known input.

None of these are AST stubs, so bob's stub/mock detector does not catch them.
The fix lives at *extraction* time: a parity/equivalence AC MUST use the
RANDOMIZED-INPUT form (inputs drawn from a per-test seed; expected values
precomputed by the reference at test-generation time and replayed) and, where
the feature has a separately-observable execution substrate (kernel launch
counter, subprocess, external library call), it SHOULD add an
EXECUTION-EVIDENCE check that the real work path actually ran.

This module is the hippy-side entry point. The synthesis logic is shared with
``bob.spec_quality.parity_test_anti_cheat``; here we re-export it and add
``requires_execution_evidence`` — the predicate the hippy synthesizer uses to
decide whether a parity intent also needs the execution-evidence AC.
"""

from __future__ import annotations

from bob.spec_quality.parity_test_anti_cheat import (  # noqa: F401
    ensure_randomized_parity_coverage,
    has_execution_substrate,
    is_parity_intent,
)
from bob.spec_quality.parity_test_anti_cheat import (
    synthesize_parity_ac as _synthesize_parity_ac,
)

__all__ = [
    "synthesize_parity_ac",
    "requires_execution_evidence",
    "is_parity_intent",
    "has_execution_substrate",
    "ensure_randomized_parity_coverage",
]


def synthesize_parity_ac(
    intent: str,
    *,
    num_seeds: int = 32,
    execution_substrate: bool | None = None,
) -> list[str]:
    """Synthesize the randomized-input parity AC shape for a parity *intent*.

    hippy-side entry point delegating to the shared bob synthesis core. Returns
    a ``property:`` AC asserting output matches the reference over N randomized
    seeds (expected values precomputed at test-generation time and replayed),
    optionally followed by a ``behavior:`` execution-evidence AC when the intent
    has an observable substrate. Returns ``[]`` for a non-parity intent.

    Raises ValueError on invalid *intent*, *num_seeds*, or *execution_substrate*
    (see ``bob.spec_quality.parity_test_anti_cheat.synthesize_parity_ac``).
    """
    return _synthesize_parity_ac(
        intent, num_seeds=num_seeds, execution_substrate=execution_substrate
    )


def requires_execution_evidence(intent: str) -> bool:
    """Return True iff a parity *intent* also needs an execution-evidence AC.

    An execution-evidence AC is warranted only when the feature is both:

      * a parity/equivalence intent (its acceptance is output-equals-reference),
        AND
      * backed by a separately-observable execution substrate (a kernel-launch
        counter, subprocess, external library/FFI call, …).

    A pure-numeric parity feature with no observable substrate returns False:
    there is nothing extra to assert that the real work path ran. A non-parity
    intent also returns False — evidence checks attach only to parity ACs.

    Raises
    ------
    ValueError
        If *intent* is not a str.
    """
    return is_parity_intent(intent) and has_execution_substrate(intent)
