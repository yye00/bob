"""AC repairer with semantic-equivalence verification (F-d0402eb0).

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob.ac_repairer import repair_smelly_acs, verify_semantic_equivalence

    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)

    result = repair_smelly_acs(
        feature_id="feat-001",
        acceptance_criteria=["The system should process requests."],
        auto_repair=True,
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts
    result["smell_findings"]   # list of SmellFinding

Integration with bob.spec_critic::

    from bob.ac_repairer import repair_smelly_acs

    result = repair_smelly_acs(
        feature_id=feature_id,
        acceptance_criteria=acs,
    )
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REPAIRS_LOG = _WORKSPACE_ROOT / "repairs.log"

_EQUIVALENCE_PROMPT_TEMPLATE = """\
You are a requirements auditor. Determine whether the following rewritten requirement \
imposes the same observable behavioral constraint as the original.

Original:
  {original}

Rewrite:
  {rewrite}

Answer on the first line with exactly: EQUIVALENT: true  OR  EQUIVALENT: false
Then on the next line: RATIONALE: <one sentence explanation>

Do not add anything else.
"""

_REWRITE_PROMPT_TEMPLATE = """\
You are a requirements engineer. The following acceptance criterion has a smell: {smell_name} ({smell_id}).

Original criterion:
  {original}

Smell detail:
  {detail}

Rewrite the criterion to eliminate the smell while preserving the exact same observable behavior and constraint.
Output ONLY the rewritten criterion text, no explanation.
"""


def _call_llm_judge(prompt: str) -> Any:
    """Call the LLM judge synchronously. Isolated so tests can patch it."""
    import anthropic  # type: ignore[import]

    client = anthropic.Anthropic()
    return client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )


def _parse_equivalence_response(text: str) -> tuple[bool, str]:
    """Parse the structured equivalence judge response."""
    equiv_match = re.search(r"EQUIVALENT:\s*(true|false)", text, re.IGNORECASE)
    rationale_match = re.search(r"RATIONALE:\s*(.+)", text, re.IGNORECASE)
    rationale = rationale_match.group(1).strip() if rationale_match else text
    if not equiv_match:
        return False, rationale or "Could not parse judge response"
    is_equiv = equiv_match.group(1).lower() == "true"
    return is_equiv, rationale


def verify_semantic_equivalence(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Check whether rewrite is semantically equivalent to original via LLM judge.

    Parameters
    ----------
    original:
        The original acceptance criterion text.
    rewrite:
        The rewritten acceptance criterion text.

    Returns
    -------
    tuple[bool, str]
        (is_equivalent, rationale). On any LLM error returns (False, error_message).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    if not isinstance(original, str):
        raise ValueError(f"original must be a string, got {type(original).__name__}")
    if not isinstance(rewrite, str):
        raise ValueError(f"rewrite must be a string, got {type(rewrite).__name__}")

    prompt = _EQUIVALENCE_PROMPT_TEMPLATE.format(original=original, rewrite=rewrite)
    try:
        response = _call_llm_judge(prompt)
        text = response.content[0].text.strip() if response.content else ""
    except Exception as exc:
        return False, f"LLM judge call failed: {exc}"

    return _parse_equivalence_response(text)


def _generate_rewrite(finding: Any) -> str | None:
    """Generate a suggested rewrite for a smell finding via LLM."""
    if hasattr(finding, "severity"):
        severity = finding.severity
        smell_id = finding.smell_id
        smell_name = finding.smell_name
        text = finding.text
        detail = finding.detail
    else:
        severity = finding.get("severity", "")
        smell_id = finding.get("smell_id", "")
        smell_name = finding.get("smell_name", "")
        text = finding.get("text", "")
        detail = finding.get("detail", "")

    if severity == "I":
        return None

    prompt = _REWRITE_PROMPT_TEMPLATE.format(
        smell_id=smell_id,
        smell_name=smell_name,
        original=text,
        detail=detail,
    )
    try:
        response = _call_llm_judge(prompt)
        result_text = response.content[0].text.strip() if response.content else ""
        return result_text if result_text else None
    except Exception as exc:
        logger.warning("generate_rewrite LLM call failed: %s", exc)
        return None


def _log_repair(repair: dict[str, Any], repairs_log: Path) -> None:
    """Append a repair entry to the repairs log."""
    repairs_log.parent.mkdir(parents=True, exist_ok=True)
    with repairs_log.open("a", encoding="utf-8") as fh:
        fh.write("---\n")
        fh.write(yaml.dump(repair, default_flow_style=False, allow_unicode=True))


def repair_smelly_acs(
    feature_id: str,
    acceptance_criteria: list[str],
    auto_repair: bool = True,
    repairs_log: Path | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Detect smells in ACs, verify rewrites semantically, and auto-apply ERROR repairs.

    For each smell finding, the linter emits a suggested_rewrite. A separate
    LLM judge verifies semantic equivalence between the original and proposed
    rewrite. Only rewrites that pass the equivalence check and belong to
    ERROR-severity smells are auto-applied. Per-feature opt-out via auto_repair=False.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    acceptance_criteria:
        List of AC strings to inspect and potentially repair.
    auto_repair:
        When False, detection and rewrite generation run but no rewrites are
        applied (per-feature opt-out).
    repairs_log:
        Path to append repair records. Defaults to ``repairs.log`` in workspace root.
    known_feature_ids:
        Set of valid feature IDs in the spec (used by smell detectors).

    Returns
    -------
    dict with keys:
        - ``repaired_acs``: list[str] — ACs with ERROR-smell repairs applied
        - ``repairs_applied``: list[dict] — repair records
        - ``smell_findings``: list[SmellFinding] — all detected findings
        - ``auto_repair_enabled``: bool — mirrors the ``auto_repair`` parameter

    Raises
    ------
    ValueError
        If feature_id is not a string or acceptance_criteria is not a list.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a string, got {type(feature_id).__name__}")
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )

    from bob.spec_quality.ac_auto_repair import repair_feature_acs

    result = repair_feature_acs(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        auto_repair=auto_repair,
        repairs_log=repairs_log,
        known_feature_ids=known_feature_ids,
    )
    result["auto_repair_enabled"] = auto_repair
    return result


__all__ = [
    "repair_smelly_acs",
    "verify_semantic_equivalence",
]
