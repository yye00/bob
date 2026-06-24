"""bob75.implementer — Implementer gate for Devin-style editable plan.yaml gate.

Implementer sub-agents call ``check_plan_approved`` at the start of any
code-generation work to enforce the plan gate. If plan.yaml is absent or
``approved: false``, the function raises ``ImplementerBlockedError`` so work
cannot begin without human sign-off.

Public API::

    from bob75.implementer import check_plan_approved

    check_plan_approved(feature_id="abc123")                        # raises if not approved
    check_plan_approved(feature_id="abc123", raise_on_blocked=False) # returns bool
"""

from __future__ import annotations

from pathlib import Path

from bob.orchestrator.plan_gate import ImplementerBlockedError, is_approved


def check_plan_approved(
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
        UUID (or short ID) of the feature whose plan.yaml to inspect.
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


__all__ = ["check_plan_approved", "ImplementerBlockedError"]
