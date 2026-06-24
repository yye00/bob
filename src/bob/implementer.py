"""bob.implementer — implementer-side gate check for the Devin-style plan.yaml gate.

Implementer sub-agents call ``validate_plan_approved`` at startup to enforce the
plan approval gate. If plan.yaml is absent or ``approved: false``, the function
raises :exc:`ImplementerBlockedError` so work cannot begin without human sign-off.

Public API::

    from bob.implementer import validate_plan_approved, check_plan_approved, check_plan_approval

    validate_plan_approved(feature_id="abc123")          # raises if not approved
    validate_plan_approved(feature_id="abc123", raise_on_blocked=False)  # returns bool
    check_plan_approved(feature_id="abc123")             # returns bool, never raises
    check_plan_approval(feature_id="abc123")             # alias for check_plan_approved
"""

from __future__ import annotations

from pathlib import Path

from bob.orchestrator.plan_gate import ImplementerBlockedError, is_approved


def validate_plan_approved(
    feature_id: str,
    workspace: Path | str | None = None,
    *,
    raise_on_blocked: bool = True,
) -> bool:
    """Return True when plan.yaml is approved; otherwise raise or return False.

    Implementer sub-agents MUST call this before performing any code-generation
    work. The function reads ``specs/<feature_id>/plan.yaml`` and checks the
    ``approved`` key.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to inspect.
    workspace:
        Override for the workspace root (defaults to CWD).
    raise_on_blocked:
        When True (default), raise :exc:`ImplementerBlockedError` if plan.yaml
        is absent or ``approved: false``. When False, return ``False`` instead
        of raising (useful for polling / conditional logic).

    Returns
    -------
    bool
        ``True`` iff plan.yaml exists and ``approved: true``.
        ``False`` only when ``raise_on_blocked=False`` and the plan is absent /
        not approved.

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None.
    ImplementerBlockedError
        When ``raise_on_blocked=True`` and the plan is absent or unapproved.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")

    approved = is_approved(feature_id, workspace)

    if not approved:
        if raise_on_blocked:
            raise ImplementerBlockedError(
                f"Implementer blocked: plan.yaml not approved for feature {feature_id}. "
                "Set approved: true in specs/<feature>/plan.yaml before running the implementer."
            )
        return False

    return True


def check_plan_approved(
    feature_id: str,
    workspace: Path | str | None = None,
) -> bool:
    """Return True when plan.yaml is approved, False otherwise — never raises.

    A non-raising convenience wrapper around :func:`validate_plan_approved`
    for use in polling loops or conditional logic where raising an exception
    is not appropriate.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to inspect.
    workspace:
        Override for the workspace root (defaults to CWD).

    Returns
    -------
    bool
        ``True`` iff plan.yaml exists and ``approved: true``.
        ``False`` when plan.yaml is absent or ``approved: false``.

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    return is_approved(feature_id, workspace)


def check_plan_approval(
    feature_id: str,
    workspace: Path | str | None = None,
) -> bool:
    """Alias for :func:`check_plan_approved` — returns True when plan.yaml is approved.

    Implementer sub-agents may call this to check the gate without raising an
    exception.  Returns False (never raises) when plan.yaml is absent or not
    approved.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to inspect.
    workspace:
        Override for the workspace root (defaults to CWD).

    Returns
    -------
    bool
        ``True`` iff plan.yaml exists and ``approved: true``.
        ``False`` when plan.yaml is absent or ``approved: false``.

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None.
    """
    return check_plan_approved(feature_id, workspace)
