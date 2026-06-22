"""AC repair with semantic-equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob3.ac_repair import check_semantic_equivalence, auto_repair_ac

    is_equiv, rationale = check_semantic_equivalence(original, rewrite)

    result = auto_repair_ac(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts

Integration with bob3.linter::

    from bob3.linter import detect_smells
    from bob3.ac_repair import auto_repair_ac

    findings = detect_smells(ac_text)
    result = auto_repair_ac(
        feature_id=feature_id,
        findings=findings,
        original_acs=[ac_text],
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


def check_semantic_equivalence(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Check whether rewrite is semantically equivalent to original via LLM judge.

    Feeds original + rewrite to a separate LLM judge. If the judge cannot infer
    they impose the same observable constraint, returns (False, rationale).

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


def _log_repair(repair: dict[str, Any], repairs_log: Path) -> None:
    """Append a repair entry to the repairs log."""
    repairs_log.parent.mkdir(parents=True, exist_ok=True)
    with repairs_log.open("a", encoding="utf-8") as fh:
        fh.write("---\n")
        fh.write(yaml.dump(repair, default_flow_style=False, allow_unicode=True))


def _coerce_finding(raw: Any) -> dict[str, Any]:
    """Coerce a SmellFinding (namedtuple/dataclass/dict) to a plain dict."""
    if hasattr(raw, "_asdict"):
        return raw._asdict()
    if hasattr(raw, "__dict__"):
        return vars(raw)
    if isinstance(raw, dict):
        return raw
    raise ValueError(f"finding must be a dict or named object, got {type(raw).__name__}")


def auto_repair_ac(
    feature_id: str,
    findings: list[Any],
    original_acs: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Apply auto-repairs for ERROR-severity findings that pass equivalence check.

    Integrates with bob3.linter: pass SmellFinding objects produced by
    ``bob3.linter.detect_smells`` as the ``findings`` parameter.

    For each ERROR-severity finding with a suggested_rewrite, feeds the original
    and rewrite to an LLM judge. Only rewrites confirmed as semantically
    equivalent are applied. Per-feature opt-out via auto_repair=False.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    findings:
        List of smell finding dicts or SmellFinding objects. Each must have:
        smell_id, smell_name, severity, text, detail, suggested_rewrite.
    original_acs:
        The original list of acceptance criteria strings.
    repairs_log:
        Path to append repair records. Defaults to ``repairs.log`` in workspace root.
    auto_repair:
        When False, detection runs but no rewrites are applied (per-feature opt-out).

    Returns
    -------
    dict with keys:
        - ``repaired_acs``: list[str] — ACs with ERROR-smell repairs applied
        - ``repairs_applied``: list[dict] — repair records

    Raises
    ------
    ValueError
        If feature_id is not a string, findings is not a list, or original_acs is not a list.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a string, got {type(feature_id).__name__}")
    if not isinstance(findings, list):
        raise ValueError(f"findings must be a list, got {type(findings).__name__}")
    if not isinstance(original_acs, list):
        raise ValueError(f"original_acs must be a list, got {type(original_acs).__name__}")

    repairs_log = repairs_log or _DEFAULT_REPAIRS_LOG
    applied: list[dict[str, Any]] = []
    repair_map: dict[str, str] = {}

    if auto_repair:
        for raw_finding in findings:
            finding = _coerce_finding(raw_finding)

            if finding.get("severity") != "E":
                continue

            rewrite = finding.get("suggested_rewrite")
            if rewrite is None:
                continue

            is_equiv, rationale = check_semantic_equivalence(finding["text"], rewrite)
            if not is_equiv:
                continue

            repair = {
                "feature_id": feature_id,
                "smell_id": finding["smell_id"],
                "smell_name": finding["smell_name"],
                "original": finding["text"],
                "rewrite": rewrite,
                "rationale": rationale,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            applied.append(repair)
            repair_map[finding["text"]] = rewrite
            _log_repair(repair, repairs_log)

    repaired_acs = [repair_map.get(ac, ac) for ac in original_acs]

    return {
        "repaired_acs": repaired_acs,
        "repairs_applied": applied,
    }


def suggest_rewrite(finding: Any) -> str | None:
    """Return the suggested_rewrite for a smell finding, or None if absent.

    Per-smell, the linter emits a suggested_rewrite string alongside the
    finding. This function extracts that string from a finding dict or
    SmellFinding namedtuple.

    Parameters
    ----------
    finding:
        A smell finding dict or SmellFinding namedtuple with a
        ``suggested_rewrite`` field.

    Returns
    -------
    str | None
        The suggested rewrite text, or None when the finding carries no
        suggested_rewrite.

    Raises
    ------
    ValueError
        If the finding is not a dict or named object.
    """
    coerced = _coerce_finding(finding)
    return coerced.get("suggested_rewrite")


def apply_repair(original_ac: str, rewrite: str) -> str:
    """Apply a repair by replacing original_ac with rewrite.

    Validates that both arguments are strings and returns the rewrite as
    the repaired AC text.

    Parameters
    ----------
    original_ac:
        The original acceptance criterion text to be replaced.
    rewrite:
        The new text to substitute in place of the original.

    Returns
    -------
    str
        The rewrite text (the repaired acceptance criterion).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    if not isinstance(original_ac, str):
        raise ValueError(f"original_ac must be a string, got {type(original_ac).__name__}")
    if not isinstance(rewrite, str):
        raise ValueError(f"rewrite must be a string, got {type(rewrite).__name__}")
    return rewrite


# Canonical names required by acceptance criteria — alias the implementations
verify_semantic_equivalence = check_semantic_equivalence
auto_repair_smelly_acs = auto_repair_ac
