"""Devin-style editable plan.yaml gate before any implementer fires (F-0bf30902).

After F-R7-450 spec-critic passes, write specs/<feature>/plan.yaml and emit a
structured PLAN_READY event. Implementer sub-agents refuse to start unless
plan.yaml.approved is true (either set by human or by --auto-approve in CI).
Edits to plan.yaml re-trigger F-R7-450 critic incrementally via F-R7-451 provenance.

Public API::

    from bob.orchestrator.plan_gate import write_plan_artifact, is_approved

    path = write_plan_artifact(feature_id="abc123", name="My feature",
                               description="...", acceptance_criteria=[...])
    approved = is_approved(feature_id="abc123")
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImplementerBlockedError(RuntimeError):
    """Raised when an implementer sub-agent tries to start without approval."""


class PlanArtifactMissingError(FileNotFoundError):
    """Raised when specs/<feature>/plan.yaml is expected but absent."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPECS_ROOT = Path("specs")
_PLAN_FILENAME = "plan.yaml"


def _specs_root(workspace: str | Path | None = None) -> Path:
    """Return the specs root directory, relative to workspace or CWD."""
    base = Path(workspace) if workspace else Path.cwd()
    return base / _SPECS_ROOT


def _plan_path(feature_id: str, workspace: str | Path | None = None) -> Path:
    return _specs_root(workspace) / feature_id / _PLAN_FILENAME


def _spec_hash(acceptance_criteria: list[str]) -> str:
    payload = "\n".join(acceptance_criteria or [])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def write_plan_artifact(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: str | Path | None = None,
    *,
    auto_approve: bool = False,
) -> Path:
    """Write specs/<feature_id>/plan.yaml and return the path.

    The file is written with ``approved: false`` by default so implementers
    refuse to start until a human (or CI --auto-approve flag) sets it to true.

    Preserves any prior ``approved`` value if the file already exists and the
    spec hash has not changed (idempotent re-generation).

    Args:
        feature_id: UUID of the feature.
        name: Human-readable feature name.
        description: Feature description text.
        acceptance_criteria: List of AC strings.
        workspace: Override for the workspace root (defaults to CWD).
        auto_approve: When True, writes ``approved: true`` unconditionally.
            Intended for CI / --auto-approve paths.

    Returns:
        Absolute Path to the written plan.yaml.

    Raises:
        ValueError: When feature_id is empty/None, name is empty/None,
            or acceptance_criteria is not a list.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    if not name or not isinstance(name, str):
        raise ValueError("name must be a non-empty string")
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )

    plan_path = _plan_path(feature_id, workspace)
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    new_hash = _spec_hash(acceptance_criteria)
    approved = auto_approve

    # Preserve prior approval when the spec hash has not changed.
    if not auto_approve and plan_path.exists():
        try:
            existing = yaml.safe_load(plan_path.read_text()) or {}
            if (
                existing.get("spec_hash") == new_hash
                and existing.get("approved") is True
            ):
                approved = True
        except Exception:
            pass  # corrupt file — overwrite cleanly

    plan: dict[str, Any] = {
        "feature_id": feature_id,
        "name": name,
        "description": description or "",
        "acceptance_criteria": acceptance_criteria,
        "approved": approved,
        "spec_hash": new_hash,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }

    plan_path.write_text(yaml.dump(plan, sort_keys=False, allow_unicode=True))
    logger.info(
        "PLAN_READY feature_id=%s path=%s approved=%s",
        feature_id[:8],
        plan_path,
        approved,
    )

    # Append PLAN_READY event to runs/events.jsonl
    _emit_plan_ready_event(feature_id, str(plan_path), approved, workspace)

    return plan_path.resolve()


def is_approved(
    feature_id: str,
    workspace: str | Path | None = None,
) -> bool:
    """Return True iff specs/<feature_id>/plan.yaml exists and approved=true.

    An absent file is treated as unapproved (safe default — implementer blocks).
    A malformed file is treated as unapproved with a warning.
    """
    plan_path = _plan_path(feature_id, workspace)
    if not plan_path.exists():
        logger.debug("plan_gate: plan.yaml missing for %s — not approved", feature_id[:8])
        return False
    try:
        data = yaml.safe_load(plan_path.read_text()) or {}
        approved = bool(data.get("approved", False))
        return approved
    except Exception as exc:
        logger.warning(
            "plan_gate: malformed plan.yaml for %s (%s) — treating as unapproved",
            feature_id[:8],
            exc,
        )
        return False


def approve_plan(
    feature_id: str,
    workspace: str | Path | None = None,
) -> bool:
    """Set approved=true in plan.yaml in-place.

    Returns True on success, False if plan.yaml does not exist.
    """
    plan_path = _plan_path(feature_id, workspace)
    if not plan_path.exists():
        logger.warning("plan_gate: cannot approve — plan.yaml missing for %s", feature_id[:8])
        return False
    try:
        data = yaml.safe_load(plan_path.read_text()) or {}
        data["approved"] = True
        plan_path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True))
        logger.info("plan_gate: approved plan for %s", feature_id[:8])
        return True
    except Exception as exc:
        logger.error("plan_gate: failed to approve plan for %s: %s", feature_id[:8], exc)
        return False


def load_plan(
    feature_id: str,
    workspace: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load plan.yaml for a feature, returning None if absent or malformed."""
    plan_path = _plan_path(feature_id, workspace)
    if not plan_path.exists():
        return None
    try:
        return yaml.safe_load(plan_path.read_text()) or {}
    except Exception:
        return None


def compute_plan_vs_spec_drift(
    feature_id: str,
    current_acceptance_criteria: list[str],
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Compute drift between plan.yaml AC and current spec AC.

    Returns a dict with:
        - ``spec_hash_plan``: hash recorded in plan.yaml
        - ``spec_hash_current``: hash of current AC
        - ``drift``: True iff hashes differ
        - ``added``: ACs present in current but not in plan
        - ``removed``: ACs present in plan but not in current
    """
    plan = load_plan(feature_id, workspace) or {}
    plan_ac: list[str] = plan.get("acceptance_criteria") or []
    plan_hash = plan.get("spec_hash", "")
    current_hash = _spec_hash(current_acceptance_criteria)

    plan_set = set(plan_ac)
    current_set = set(current_acceptance_criteria)

    return {
        "spec_hash_plan": plan_hash,
        "spec_hash_current": current_hash,
        "drift": plan_hash != current_hash,
        "added": sorted(current_set - plan_set),
        "removed": sorted(plan_set - current_set),
    }


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


def emit_plan_ready_event(
    feature_id: str,
    plan_path: str,
    approved: bool,
    workspace: str | Path | None = None,
) -> None:
    """Append a PLAN_READY JSON event line to runs/events.jsonl (public API)."""
    _emit_plan_ready_event(feature_id, plan_path, approved, workspace)


def _emit_plan_ready_event(
    feature_id: str,
    plan_path: str,
    approved: bool,
    workspace: str | Path | None = None,
) -> None:
    """Append a PLAN_READY JSON event line to runs/events.jsonl."""
    base = Path(workspace) if workspace else Path.cwd()
    events_path = base / "runs" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "event": "PLAN_READY",
        "feature_id": feature_id,
        "plan_path": plan_path,
        "approved": approved,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Gate functions
# ---------------------------------------------------------------------------


def refuse_implementer_when_unapproved(
    feature_id: str,
    workspace: str | Path | None = None,
) -> None:
    """Raise ImplementerBlockedError when plan.yaml.approved is False.

    Call this at the top of any implementer sub-agent to enforce the gate.
    Raises ImplementerBlockedError if the plan is absent or not approved.
    """
    if not is_approved(feature_id, workspace):
        raise ImplementerBlockedError(
            f"Implementer blocked: plan.yaml not approved for feature {feature_id}. "
            "Set approved: true in specs/<feature>/plan.yaml before running the implementer."
        )


def handle_missing_plan_yaml(
    feature_id: str,
    workspace: str | Path | None = None,
) -> None:
    """Raise PlanArtifactMissingError when specs/<feature>/plan.yaml is absent.

    Use this to enforce that plan.yaml must exist before any downstream step.
    Raises PlanArtifactMissingError with a message containing "plan.yaml".
    """
    plan_path = _plan_path(feature_id, workspace)
    if not plan_path.exists():
        raise PlanArtifactMissingError(
            f"plan.yaml not found for feature {feature_id}: {plan_path}. "
            "Run write_plan_artifact() first."
        )


# ---------------------------------------------------------------------------
# Diff / unified-diff
# ---------------------------------------------------------------------------


def diff_plan_vs_spec(
    feature_id: str,
    current_acceptance_criteria: list[str],
    workspace: str | Path | None = None,
) -> str:
    """Return a unified-diff string comparing plan.yaml ACs vs current spec ACs.

    The diff is in standard unified-diff format (--- / +++ / @@ markers).
    Returns an empty string when there is no drift.
    """
    plan = load_plan(feature_id, workspace) or {}
    plan_ac: list[str] = plan.get("acceptance_criteria") or []

    plan_lines = [ac + "\n" for ac in plan_ac]
    current_lines = [ac + "\n" for ac in current_acceptance_criteria]

    diff = list(
        difflib.unified_diff(
            plan_lines,
            current_lines,
            fromfile="plan.yaml (recorded AC)",
            tofile="spec (current AC)",
        )
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# Critic re-trigger
# ---------------------------------------------------------------------------


def retrigger_critic_on_edit(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: str | Path | None = None,
) -> list[Any]:
    """Call spec_critic.critique_feature incrementally when plan.yaml drifts.

    Detects drift via compute_plan_vs_spec_drift; if drift is found, calls
    bob.spec_quality.spec_critic.critique_feature and returns the defect list.
    Returns an empty list if no drift is detected (no re-trigger needed).
    """
    drift_report = compute_plan_vs_spec_drift(feature_id, acceptance_criteria, workspace)
    if not drift_report["drift"]:
        logger.debug("plan_gate: no drift for %s — skipping critic re-trigger", feature_id[:8])
        return []

    logger.info(
        "plan_gate: drift detected for %s — re-triggering spec critic incrementally",
        feature_id[:8],
    )
    from bob.spec_quality.spec_critic import critique_feature  # local import avoids circular dep

    defects = critique_feature(
        feature_id=feature_id,
        name=name,
        description=description or "",
        acceptance_criteria=acceptance_criteria,
    )
    return defects
