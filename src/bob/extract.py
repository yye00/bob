"""Feature extraction helpers — unique spec_slot assignment.

Feature 24c307e5-e761-43e0-b44d-85dd268ab520.

Regression this guards against
------------------------------
``extract-from-peas`` once emitted three feature rows sharing spec_slot
``F-R7-003``. Because the scheduler keyed runnable/claim eligibility on
spec_slot, a completed sibling drove the runnable-count for a still-pending
feature to 0 and the build STOPPED (QUEUE_DRAINED) with real work left.

The write-time fix lives here: every feature MUST carry a unique spec_slot.
On collision, the first occurrence keeps its original slot and later ones get
a deterministic ``#N`` suffix. A feature that has no spec_slot derives one
from its ``key`` (cross-generation label) or, failing that, its unique ``id``.

``spec_slot`` remains a cross-generation matching label only (per F-R7-400);
scheduling decisions are keyed on the feature's unique ``id`` — see
:func:`bob.scheduler.compute_runnable`.
"""

from __future__ import annotations

from typing import Any


def _base_slot(feature: dict[str, Any]) -> str:
    """Return the slot to seed disambiguation from.

    Preference order: explicit ``spec_slot``, then the cross-generation
    ``key``, then the unique ``id``. Raises ValueError if none is present —
    a feature with no identity at all cannot be given a stable slot.
    """
    for name in ("spec_slot", "key", "id"):
        value = feature.get(name)
        if value not in (None, ""):
            return str(value)
    raise ValueError(f"feature has no spec_slot, key, or id: {feature!r}")


def assign_unique_spec_slot(features: Any) -> list[dict[str, Any]]:
    """Return *features* with a unique ``spec_slot`` on every entry.

    The first feature to use a given slot keeps it unchanged; every later
    collision is suffixed deterministically (``F-R7-003#1``, ``F-R7-003#2``,
    …) so the result set has no duplicate spec_slots. Features are copied, not
    mutated in place, and all other fields are preserved.

    Args:
        features: A list of feature mappings. Each must expose at least one of
            ``spec_slot``, ``key``, or ``id`` to derive a slot from.

    Returns:
        A new list of feature dicts, in input order, each with a unique
        ``spec_slot``. Empty list for empty input.

    Raises:
        ValueError: if *features* is not a list, or any feature has no
            ``spec_slot``, ``key``, or ``id`` to derive a slot from.
    """
    if not isinstance(features, list):
        raise ValueError(
            f"features must be a list, got {type(features).__name__}"
        )

    emitted: set[str] = set()
    out: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError(
                f"each feature must be a mapping, got {type(feature).__name__}"
            )
        base = _base_slot(feature)
        slot = base
        suffix = 0
        while slot in emitted:
            suffix += 1
            slot = f"{base}#{suffix}"
        emitted.add(slot)
        new_feature = dict(feature)
        new_feature["spec_slot"] = slot
        out.append(new_feature)
    return out
