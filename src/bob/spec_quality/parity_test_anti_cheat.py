"""Parity-test anti-cheat: randomized-input + execution-evidence AC synthesis.

Feature 8ff7325a-aab0-43f3-89e9-ce039e624cee.

A *parity* (a.k.a. equivalence) acceptance criterion checks an implementation's
output against a reference implementation. Discovered during the hippy/hipsci
spec cross-review: proving an op correct by comparing its output to a SINGLE
frozen expected value is gameable three ways by an attempt-pressured builder
without doing the real work:

  (a) emit a kernel/function that returns the baked-in constant the test checks;
  (b) compute on the host (numpy / pure Python) and disguise it behind a
      device-copy so it "looks" like the target substrate;
  (c) special-case the one known input.

None of these are AST stubs, so bob's stub/mock detector does not catch them.
The fix lives at *extraction* time (spec-over-code-fix): when the synthesizer
emits a parity/equivalence AC it MUST prefer the RANDOMIZED-INPUT form over a
lone frozen value —

  * inputs are drawn at test time from a per-test seed;
  * expected values are precomputed by the reference over many seeds at
    test-GENERATION time and replayed, so the implementation can never see or
    call the reference at run time;

and, where the feature has a separately-observable execution substrate (kernel
launch counter, subprocess, external library call), the AC SHOULD add an
EXECUTION-EVIDENCE check that the real work path actually ran — so a
constant-returning or wrong-substrate implementation fails even when its
numbers match.

Boundary (never weaken structure): features with genuinely fixed, enumerable
expected outputs (a constant table, one canonical vector) may keep a frozen AC
but MUST still carry at least one randomized/property AC alongside it. This
module only ADDS an AC shape; it never removes or rewrites an existing
structural AC.

Public API
----------
synthesize_parity_ac(intent, *, num_seeds=32, execution_substrate=None)
    -> list[str]
    The recognized AC shape. Returns randomized-seed parity AC(s) (plus an
    execution-evidence AC when a substrate is observable) for a parity intent,
    or ``[]`` for a non-parity intent.

ensure_randomized_parity_coverage(criteria, *, intent, num_seeds=32)
    -> list[str]
    Given an existing AC list and the feature intent, append a randomized
    parity AC when the intent is parity-shaped and no randomized AC is present.
    Existing structural ACs are always preserved.

is_parity_intent(text) -> bool
has_execution_substrate(text) -> bool
    Predicates used by the above and re-usable by the synthesizer.
"""

from __future__ import annotations

import re

# Minimum number of randomized seeds. A single seed is still effectively a lone
# frozen input, so anything below this is promoted up.
_MIN_SEEDS = 8
_DEFAULT_SEEDS = 32

# Phrases that signal an output-equals-reference (parity / equivalence) intent.
_PARITY_MARKERS = (
    "parity",
    "equivalence",
    "equivalent to",
    "output equals",
    "output must equal",
    "equals the reference",
    "equals reference",
    "equal the reference",
    "matches the reference",
    "matches reference",
    "match the reference",
    "match reference",
    "matches the numpy",
    "match the numpy",
    "matches numpy",
    "matches the scipy",
    "match the scipy",
    "matches scipy",
    "compared to the reference",
    "against the reference",
    "reference implementation",
    "reference value",
    "golden value",
    "expected value",
    "bit-for-bit",
    "bitwise identical",
    "numerically identical",
)

# Markers of a separately-observable execution substrate: if the real work path
# is observable, a constant-returning / wrong-substrate impl can be caught.
_SUBSTRATE_MARKERS = (
    "kernel",
    "kernel launch",
    "launch count",
    "gpu",
    "cuda",
    "device",
    "subprocess",
    "shell out",
    "shells out",
    "spawn",
    "external library",
    "external call",
    "ffi",
    "syscall",
    "instruction count",
    "trace",
)


def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a str, got {type(value).__name__!r}")
    return value


def is_parity_intent(text: str) -> bool:
    """Return True iff *text* describes an output-equals-reference intent.

    Raises ValueError if *text* is not a str.
    """
    text = _require_str(text, "text")
    low = text.lower()
    return any(marker in low for marker in _PARITY_MARKERS)


def has_execution_substrate(text: str) -> bool:
    """Return True iff *text* describes a separately-observable execution substrate.

    Raises ValueError if *text* is not a str.
    """
    text = _require_str(text, "text")
    low = text.lower()
    return any(marker in low for marker in _SUBSTRATE_MARKERS)


def _normalize_seeds(num_seeds: object) -> int:
    """Coerce *num_seeds* to a sane seed count.

    - non-int (and bool, which is an int subclass) -> ValueError
    - negative -> ValueError
    - 0 -> default
    - below the minimum -> promoted to the minimum
    """
    if isinstance(num_seeds, bool) or not isinstance(num_seeds, int):
        raise ValueError(
            f"num_seeds must be an int, got {type(num_seeds).__name__!r}"
        )
    if num_seeds < 0:
        raise ValueError(f"num_seeds must be >= 0, got {num_seeds}")
    if num_seeds == 0:
        return _DEFAULT_SEEDS
    return max(num_seeds, _MIN_SEEDS)


def synthesize_parity_ac(
    intent: str,
    *,
    num_seeds: int = _DEFAULT_SEEDS,
    execution_substrate: bool | None = None,
) -> list[str]:
    """Synthesize the randomized-input parity AC shape for a parity *intent*.

    Parameters
    ----------
    intent:
        The feature intent text (title + description). If it is not a
        parity/equivalence intent, returns ``[]``.
    num_seeds:
        Number of randomized seeds to assert over. ``0`` uses the default;
        values below the minimum are promoted; negatives raise ValueError.
    execution_substrate:
        Tri-state. ``None`` (default) auto-detects from *intent*; ``True`` /
        ``False`` force the execution-evidence AC on/off.

    Returns
    -------
    list[str]
        A ``property:`` AC asserting output matches the reference over N
        randomized seeds (expected values precomputed at generation time and
        replayed), optionally followed by a ``behavior:`` execution-evidence
        AC. Empty for non-parity intents.

    Raises
    ------
    ValueError
        If *intent* is not a str, *num_seeds* is invalid, or
        *execution_substrate* is not a bool/None.
    """
    intent = _require_str(intent, "intent")
    if execution_substrate is not None and not isinstance(execution_substrate, bool):
        raise ValueError(
            "execution_substrate must be a bool or None, got "
            f"{type(execution_substrate).__name__!r}"
        )
    seeds = _normalize_seeds(num_seeds)

    if not is_parity_intent(intent):
        return []

    acs: list[str] = [
        (
            f"property: implementation output matches the reference over "
            f"{seeds} randomized seeds — inputs are drawn at test time from a "
            f"per-test seed and the expected values are precomputed by the "
            f"reference at test-generation time and replayed (the "
            f"implementation never sees or calls the reference at run time), "
            f"so a frozen single-input, host-computed, or special-cased "
            f"implementation fails."
        )
    ]

    want_substrate = (
        has_execution_substrate(intent)
        if execution_substrate is None
        else execution_substrate
    )
    if want_substrate:
        acs.append(
            "behavior: WHEN the parity test runs THEN an execution-evidence "
            "check (e.g. a kernel-launch counter, subprocess invocation, or "
            "external-call hook) MUST show the real work path advanced, so a "
            "constant-returning or wrong-substrate implementation fails even "
            "when its numbers match."
        )
    return acs


def _has_randomized_parity_ac(criteria: list[str]) -> bool:
    """True iff *criteria* already contains a randomized-seed parity AC."""
    for c in criteria:
        low = c.lower()
        if ("random" in low and "seed" in low) and (
            "reference" in low or "parity" in low or "matches" in low
        ):
            return True
    return False


def ensure_randomized_parity_coverage(
    criteria: list[str],
    *,
    intent: str,
    num_seeds: int = _DEFAULT_SEEDS,
) -> list[str]:
    """Append a randomized parity AC to *criteria* when *intent* is parity-shaped.

    Existing structural ACs are always preserved (this only appends). When the
    intent is not parity-shaped, or a randomized parity AC is already present,
    *criteria* is returned unchanged (a copy).

    Raises
    ------
    ValueError
        If *criteria* is not a list of str, or *intent* is not a str.
    """
    if not isinstance(criteria, list):
        raise ValueError(
            f"criteria must be a list, got {type(criteria).__name__!r}"
        )
    for i, c in enumerate(criteria):
        if not isinstance(c, str):
            raise ValueError(
                f"criteria[{i}] must be a str, got {type(c).__name__!r}"
            )
    intent = _require_str(intent, "intent")

    result = list(criteria)

    if not intent.strip() or not is_parity_intent(intent):
        return result
    if _has_randomized_parity_ac(result):
        return result

    result.extend(synthesize_parity_ac(intent, num_seeds=num_seeds))
    return result
