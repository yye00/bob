"""Semantic-equivalence verification and auto-repair of smelly ACs.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence
check feeds original + rewrite to a separate LLM judge; if it cannot infer
they impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob3.semantic_repair import verify_semantic_equivalence, apply_auto_repair

    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)

    result = apply_auto_repair(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.ac_auto_repair import (
    verify_semantic_equivalence as _verify_semantic_equivalence,
    apply_repairs,
    repair_feature_acs,
)
from bob3.linter import detect_smells, SmellFinding

__all__ = [
    "verify_semantic_equivalence",
    "apply_auto_repair",
]

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REPAIRS_LOG = _WORKSPACE_ROOT / "repairs.log"


def verify_semantic_equivalence(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Verify that rewrite is semantically equivalent to original via LLM judge.

    Parameters
    ----------
    original:
        The original acceptance criterion text.
    rewrite:
        The rewritten acceptance criterion text.

    Returns
    -------
    tuple[bool, str]
        (is_equivalent, rationale). On any error returns (False, error_message).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    if not isinstance(original, str):
        raise ValueError(f"original must be a string, got {type(original).__name__}")
    if not isinstance(rewrite, str):
        raise ValueError(f"rewrite must be a string, got {type(rewrite).__name__}")

    return _verify_semantic_equivalence(original, rewrite)


def apply_auto_repair(
    feature_id: str,
    findings: list[SmellFinding | dict[str, Any]],
    original_acs: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Apply auto-repairs for ERROR-severity findings that pass equivalence check.

    Integrates with bob3.linter: accepts SmellFinding objects or plain dicts
    with the same structure. Only ERROR-severity findings are auto-applied.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    findings:
        List of SmellFinding objects or dicts. Each must have severity, text,
        and (for dicts) suggested_rewrite.
    original_acs:
        The original list of acceptance criteria strings.
    repairs_log:
        Path to append repair records. Defaults to ``repairs.log`` in workspace root.
    auto_repair:
        When False, no rewrites are applied (per-feature opt-out).

    Returns
    -------
    dict with keys:
        - ``repaired_acs``: list[str] — ACs with ERROR-smell repairs applied
        - ``repairs_applied``: list[dict] — repair records

    Raises
    ------
    ValueError
        If feature_id is not a string, findings is not a list, or
        original_acs is not a list.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a string, got {type(feature_id).__name__}")
    if not isinstance(findings, list):
        raise ValueError(f"findings must be a list, got {type(findings).__name__}")
    if not isinstance(original_acs, list):
        raise ValueError(f"original_acs must be a list, got {type(original_acs).__name__}")

    repairs_log = repairs_log or _DEFAULT_REPAIRS_LOG

    if not auto_repair:
        return {
            "repaired_acs": list(original_acs),
            "repairs_applied": [],
        }

    import logging
    import yaml
    from datetime import datetime, timezone

    logger = logging.getLogger(__name__)
    applied: list[dict[str, Any]] = []
    repair_map: dict[str, str] = {}

    for finding in findings:
        if isinstance(finding, SmellFinding):
            severity = finding.severity
            text = finding.text
            suggested_rewrite = finding.suggested_rewrite
            smell_id = finding.smell_id
            smell_name = finding.smell_name
        else:
            severity = finding["severity"]
            text = finding["text"]
            suggested_rewrite = finding.get("suggested_rewrite")
            smell_id = finding["smell_id"]
            smell_name = finding["smell_name"]

        if severity != "E":
            continue

        if suggested_rewrite is None:
            continue

        is_equiv, rationale = verify_semantic_equivalence(text, suggested_rewrite)
        if not is_equiv:
            logger.debug("Rewrite rejected for %s (not equivalent): %s", smell_id, rationale)
            continue

        repair = {
            "feature_id": feature_id,
            "smell_id": smell_id,
            "smell_name": smell_name,
            "original": text,
            "rewrite": suggested_rewrite,
            "rationale": rationale,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        applied.append(repair)
        repair_map[text] = suggested_rewrite
        _log_repair(repair, repairs_log)

    repaired_acs = [repair_map.get(ac, ac) for ac in original_acs]

    return {
        "repaired_acs": repaired_acs,
        "repairs_applied": applied,
    }


def _log_repair(repair: dict[str, Any], repairs_log: Path) -> None:
    import yaml

    repairs_log.parent.mkdir(parents=True, exist_ok=True)
    with repairs_log.open("a", encoding="utf-8") as fh:
        fh.write("---\n")
        fh.write(yaml.dump(repair, default_flow_style=False, allow_unicode=True))
