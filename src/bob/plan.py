"""bob.plan — planning-time entry point wiring the AC-form validator.

This module is the canonical ``bob.plan`` namespace that ``bob plan --create``
uses to reject malformed acceptance criteria before a feature is persisted to
the database.  It wires :func:`bob.ac_form_validator.validate_acceptance_criteria`
into the feature-creation flow so the v.13 class of parser bugs
(Function-defined parenthetical descriptions, pytest-AC trailing prose,
pytest_scoper module-seed parens) is caught at the source instead of being
patched one downstream consumer at a time.

Usage (invoked internally by ``bob plan --create``)::

    from bob.plan import validate_plan_features

    validate_plan_features(features)
    # Raises ValueError naming every malformed criterion across all features.
"""

from __future__ import annotations

from typing import Any

from bob.ac_form_validator import MalformedACError, validate_acceptance_criteria

__all__ = [
    "validate_plan_features",
    "validate_acceptance_criteria",
    "MalformedACError",
]


def _extract_criteria(feature: dict[str, Any]) -> list[str]:
    """Return the acceptance_criteria of *feature* as a list of strings."""
    criteria = feature.get("acceptance_criteria") or []
    if isinstance(criteria, str):
        criteria = [criteria]
    return list(criteria)


def validate_plan_features(features: list[dict[str, Any]]) -> list[str]:
    """Validate the acceptance criteria of every feature at ``bob plan --create`` time.

    Runs :func:`validate_acceptance_criteria` over each feature's
    ``acceptance_criteria`` field.  Refuses to let the plan proceed (raises
    :class:`ValueError`) if any criterion across any feature is malformed, so
    malformed ACs never reach the database.

    Parameters
    ----------
    features:
        A list of feature dicts as parsed from the YAML spec.  Each may carry
        an ``acceptance_criteria`` field (list of strings, a single string, or
        be absent).

    Returns
    -------
    list[str]
        An empty list when every criterion of every feature is well-formed.

    Raises
    ------
    ValueError
        When one or more criteria are malformed.  The message names the
        offending feature and every malformed criterion so the author can
        correct them before re-submitting.
    """
    if not isinstance(features, list):
        raise TypeError(
            f"validate_plan_features expects a list of feature dicts, "
            f"got {type(features).__name__!r}"
        )

    errors: list[str] = []
    for feature in features:
        criteria = _extract_criteria(feature)
        try:
            validate_acceptance_criteria(criteria)
        except ValueError as exc:
            feature_id = feature.get("id") or feature.get("name") or "<unknown>"
            errors.append(f"feature {feature_id!r}:\n{exc}")

    if errors:
        raise ValueError(
            "malformed acceptance criteria block bob plan --create:\n\n"
            + "\n\n".join(errors)
        )
    return []
