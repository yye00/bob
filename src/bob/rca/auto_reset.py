"""F-R7-479: auto_reset submodule — re-exports should_grant_fresh_attempt.

This module exists so that ``bob.rca.auto_reset.should_grant_fresh_attempt``
satisfies the AC "Function defined: bob.rca.auto_reset.should_grant_fresh_attempt".
The canonical implementation lives in ``bob.orchestrator.rca_attempt_budget``;
this module re-exports it and adds the ``auto_reset_on_code_defect`` helper for
direct callers that prefer this namespace.
"""

from __future__ import annotations

import os
from typing import Callable

from bob.orchestrator.rca_attempt_budget import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)

__all__ = [
    "Classification",
    "classify_verification_failure",
    "should_grant_fresh_attempt",
    "auto_reset_on_code_defect",
]

_MAX_ATTEMPTS = 5


def auto_reset_on_code_defect(
    feature_id: str,
    db_update_fn: Callable[..., None],
    failed_acs: list[str],
    refinement_attempts: int,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Grant a fresh attempt when a verification failure is code-fixable.

    Delegates to the top-level ``bob.rca.auto_reset_on_code_defect``
    implementation; exposed here so callers can import from the
    ``bob.rca.auto_reset`` submodule if they prefer the granular path.
    """
    from bob.rca import auto_reset_on_code_defect as _impl

    return _impl(
        feature_id=feature_id,
        db_update_fn=db_update_fn,
        failed_acs=failed_acs,
        refinement_attempts=refinement_attempts,
        workspace=workspace,
    )
