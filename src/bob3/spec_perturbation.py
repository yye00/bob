"""Deterministic, seedable spec perturbation transforms for ablation runs.

Each transform is round-trip invertible: given the perturbed spec and the
same seed used to perturb it, invert_perturbation recovers the original.

Transforms:
  rename      – substitute identifier-like string fields with stable aliases
  reorder     – shuffle acceptance_criteria list
  red_herring – insert one extra irrelevant criterion into acceptance_criteria
"""
from __future__ import annotations

import base64
import copy
import random
from typing import Any

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_TRANSFORMS = {"rename", "reorder", "red_herring"}


def list_transforms() -> list[str]:
    """Return the sorted list of available transform names."""
    return sorted(_TRANSFORMS)

_RED_HERRING_POOL = [
    "Logging output: INFO level heartbeat emitted every 60 s",
    "File exists: src/placeholder/unused_stub.py",
    "Environment variable BOB3_NOOP_FLAG is documented",
    "Function defined: noop_identity_transform",
    "pytest: tests/test_unused_baseline.py",
    "No circular imports in package",
    "Module docstring is present",
    "Type annotations present on all public functions",
]


def perturb_spec(
    spec: dict[str, Any],
    *,
    transform: str,
    seed: int,
) -> tuple[dict[str, Any], int]:
    """Apply a named transform to *spec* using *seed* for determinism.

    Returns ``(perturbed_spec, seed)`` where ``seed`` is the same value
    passed in, retained for use by ``invert_perturbation``.
    The original *spec* dict is never mutated.
    """
    if transform not in _TRANSFORMS:
        raise ValueError(
            f"Unknown transform {transform!r}. Valid transforms: {sorted(_TRANSFORMS)}"
        )
    perturbed = copy.deepcopy(spec)
    rng = random.Random(seed)
    if transform == "rename":
        _apply_rename(perturbed, rng)
    elif transform == "reorder":
        _apply_reorder(perturbed, rng)
    elif transform == "red_herring":
        _apply_red_herring(perturbed, rng)
    return perturbed, seed


def invert_perturbation(
    perturbed: dict[str, Any],
    *,
    transform: str,
    seed: int,
) -> dict[str, Any]:
    """Recover the original spec from *perturbed* using the same *seed*.

    The *perturbed* dict is never mutated.
    """
    if transform not in _TRANSFORMS:
        raise ValueError(
            f"Unknown transform {transform!r}. Valid transforms: {sorted(_TRANSFORMS)}"
        )
    recovered = copy.deepcopy(perturbed)
    rng = random.Random(seed)
    if transform == "rename":
        _invert_rename(recovered, rng)
    elif transform == "reorder":
        _invert_reorder(recovered, rng)
    elif transform == "red_herring":
        _invert_red_herring(recovered, rng)
    return recovered


# ---------------------------------------------------------------------------
# rename – XOR-based reversible encoding keyed on seed + field index
# ---------------------------------------------------------------------------

def _xor_encode(value: str, seed: int, key_index: int) -> str:
    """Reversibly encode *value* with XOR keyed on seed and field index."""
    key = (seed * 31 + key_index * 17) & 0xFFFFFFFF
    rng_key = random.Random(key)
    buf = bytearray(value.encode("utf-8"))
    for i in range(len(buf)):
        buf[i] ^= rng_key.randint(0, 255)
    b64 = base64.urlsafe_b64encode(bytes(buf)).decode("ascii")
    return f"__perturbed_rename__{b64}"


def _xor_decode(encoded: str, seed: int, key_index: int) -> str:
    """Decode a value produced by _xor_encode."""
    prefix = "__perturbed_rename__"
    b64 = encoded[len(prefix):]
    buf = bytearray(base64.urlsafe_b64decode(b64))
    key = (seed * 31 + key_index * 17) & 0xFFFFFFFF
    rng_key = random.Random(key)
    for i in range(len(buf)):
        buf[i] ^= rng_key.randint(0, 255)
    return buf.decode("utf-8")


def _apply_rename(spec: dict[str, Any], rng: random.Random) -> None:
    """Replace identifier-like string fields with reversibly encoded aliases."""
    offset = rng.randint(0, 2**30)
    for i, key in enumerate(sorted(spec.keys())):
        val = spec[key]
        if isinstance(val, str) and " " not in val and len(val) > 0:
            spec[key] = _xor_encode(val, offset, i)


def _invert_rename(spec: dict[str, Any], rng: random.Random) -> None:
    """Decode fields encoded by _apply_rename."""
    offset = rng.randint(0, 2**30)
    for i, key in enumerate(sorted(spec.keys())):
        val = spec[key]
        if isinstance(val, str) and val.startswith("__perturbed_rename__"):
            spec[key] = _xor_decode(val, offset, i)


# ---------------------------------------------------------------------------
# reorder – shuffle acceptance_criteria and invert via permutation replay
# ---------------------------------------------------------------------------

def _apply_reorder(spec: dict[str, Any], rng: random.Random) -> None:
    """Shuffle acceptance_criteria in-place."""
    criteria = spec.get("acceptance_criteria")
    if isinstance(criteria, list) and len(criteria) > 1:
        rng.shuffle(criteria)


def _invert_reorder(spec: dict[str, Any], rng: random.Random) -> None:
    """Restore acceptance_criteria to original order by inverting the shuffle permutation."""
    criteria = spec.get("acceptance_criteria")
    if not isinstance(criteria, list) or len(criteria) <= 1:
        return
    n = len(criteria)
    # Replay Fisher-Yates: for i from n-1 down to 1, swap positions i and j=randrange(i+1)
    perm = list(range(n))
    for i in range(n - 1, 0, -1):
        j = rng.randrange(i + 1)
        perm[i], perm[j] = perm[j], perm[i]
    # perm[shuffled_pos] = original_pos — restore each element to its original position
    original_criteria: list[Any] = [None] * n
    for shuffled_pos, orig_pos in enumerate(perm):
        original_criteria[orig_pos] = criteria[shuffled_pos]
    spec["acceptance_criteria"] = original_criteria


# ---------------------------------------------------------------------------
# red_herring – insert and remove an extra irrelevant criterion
# ---------------------------------------------------------------------------

def _apply_red_herring(spec: dict[str, Any], rng: random.Random) -> None:
    """Insert one irrelevant criterion at a random position."""
    criteria = list(spec.get("acceptance_criteria", []))
    herring = rng.choice(_RED_HERRING_POOL)
    insert_pos = rng.randint(0, len(criteria))
    criteria.insert(insert_pos, herring)
    spec["acceptance_criteria"] = criteria


def _invert_red_herring(spec: dict[str, Any], rng: random.Random) -> None:
    """Remove the red-herring criterion that was inserted by _apply_red_herring."""
    criteria = list(spec.get("acceptance_criteria", []))
    herring = rng.choice(_RED_HERRING_POOL)
    # The original list had one fewer element; insert_pos was randint(0, len-1)
    insert_pos = rng.randint(0, len(criteria) - 1)
    if insert_pos < len(criteria) and criteria[insert_pos] == herring:
        criteria.pop(insert_pos)
    spec["acceptance_criteria"] = criteria
