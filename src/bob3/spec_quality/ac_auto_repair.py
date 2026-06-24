"""Auto-repair of smelly ACs with semantic-equivalence verification (F-d83eac4f).

Per the 2025 auto-repair paper (arXiv 2505.07270):
1. For each WARN/ERROR smell, generate a suggested_rewrite.
2. Feed (original, rewrite) to a separate LLM judge to verify semantic equivalence.
3. For ERROR-severity smells where equivalence passes, auto-apply the rewrite.
4. Log all repairs to repairs.log with original, rewrite, and judge rationale.
5. Per-feature opt-out via auto_repair=False.

Public API::

    from bob3.spec_quality.ac_auto_repair import (
        suggest_rewrite,
        verify_semantic_equivalence,
        apply_repairs,
        repair_feature_acs,
    )
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from bob3.spec_quality.smell_detectors import SmellFinding, detect_all

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REPAIRS_LOG = _WORKSPACE_ROOT / "repairs.log"
_METRICS_PATH = _WORKSPACE_ROOT / "reviews" / "metrics.yaml"

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_REWRITE_PROMPT_TEMPLATE = """\
You are a requirements engineer. The following acceptance criterion has a smell: {smell_name} ({smell_id}).

Original criterion:
  {original}

Smell detail:
  {detail}

Rewrite the criterion to eliminate the smell while preserving the exact same observable behavior and constraint.
Output ONLY the rewritten criterion text, no explanation.
"""

_EQUIVALENCE_PROMPT_TEMPLATE = """\
You are a requirements auditor. Determine whether the following rewritten requirement imposes the same observable behavioral constraint as the original.

Original:
  {original}

Rewrite:
  {rewrite}

Answer on the first line with exactly: EQUIVALENT: true  OR  EQUIVALENT: false
Then on the next line: RATIONALE: <one sentence explanation>

Do not add anything else.
"""

# ---------------------------------------------------------------------------
# LLM call (isolated for testability via patching)
# ---------------------------------------------------------------------------


def _call_llm_judge(prompt: str) -> Any:
    """Call the LLM judge synchronously. Isolated so tests can patch it."""
    import anthropic  # type: ignore[import]

    client = anthropic.Anthropic()
    return client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def suggest_rewrite(finding: SmellFinding | list[SmellFinding]) -> str | None | list[str | None]:
    """Generate a suggested rewrite for a smell finding or a list of findings.

    When passed a list, returns a list of rewrites (empty list for empty input).
    When passed a single SmellFinding, returns the rewritten string or None.
    Returns None for informational smells (I severity) or on LLM failure.
    """
    if isinstance(finding, list):
        return [suggest_rewrite(f) for f in finding]

    if finding.severity == "I":
        return None

    prompt = _REWRITE_PROMPT_TEMPLATE.format(
        smell_id=finding.smell_id,
        smell_name=finding.smell_name,
        original=finding.text,
        detail=finding.detail,
    )
    try:
        response = _call_llm_judge(prompt)
        text = response.content[0].text.strip() if response.content else ""
        return text if text else None
    except Exception as exc:
        logger.warning("suggest_rewrite LLM call failed for %s: %s", finding.smell_id, exc)
        return None


def verify_semantic_equivalence(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Verify that rewrite is semantically equivalent to original via LLM judge.

    Returns (is_equivalent, rationale).
    On any error or ambiguous response, returns (False, error_message).
    """
    prompt = _EQUIVALENCE_PROMPT_TEMPLATE.format(original=original, rewrite=rewrite)
    try:
        response = _call_llm_judge(prompt)
        text = response.content[0].text.strip() if response.content else ""
    except Exception as exc:
        return False, f"LLM judge call failed: {exc}"

    return _parse_equivalence_response(text)


def _parse_equivalence_response(text: str) -> tuple[bool, str]:
    """Parse the structured equivalence judge response."""
    equiv_match = re.search(r"EQUIVALENT:\s*(true|false)", text, re.IGNORECASE)
    rationale_match = re.search(r"RATIONALE:\s*(.+)", text, re.IGNORECASE)

    rationale = rationale_match.group(1).strip() if rationale_match else text

    if not equiv_match:
        return False, rationale or "Could not parse judge response"

    is_equiv = equiv_match.group(1).lower() == "true"
    return is_equiv, rationale


# ---------------------------------------------------------------------------
# Repair application
# ---------------------------------------------------------------------------


def apply_repairs(
    findings: list[SmellFinding],
    feature_id: str,
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> list[dict[str, Any]]:
    """Apply auto-repairs for ERROR-severity findings that pass equivalence check.

    Only ERROR-severity findings are auto-applied. WARN and INFO are skipped.
    Returns a list of applied repair dicts: {original, rewrite, rationale, smell_id}.
    """
    if not auto_repair:
        return []

    repairs_log = repairs_log or _DEFAULT_REPAIRS_LOG
    applied: list[dict[str, Any]] = []

    for finding in findings:
        if finding.severity != "E":
            continue

        rewrite = suggest_rewrite(finding)
        if rewrite is None:
            continue

        is_equiv, rationale = verify_semantic_equivalence(finding.text, rewrite)
        if not is_equiv:
            logger.debug(
                "Rewrite rejected for %s (not equivalent): %s", finding.smell_id, rationale
            )
            continue

        repair = {
            "feature_id": feature_id,
            "smell_id": finding.smell_id,
            "smell_name": finding.smell_name,
            "original": finding.text,
            "rewrite": rewrite,
            "rationale": rationale,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        applied.append(repair)
        _log_repair(repair, repairs_log)

    return applied


def _log_repair(repair: dict[str, Any], repairs_log: Path) -> None:
    """Append a repair entry to the repairs log."""
    repairs_log.parent.mkdir(parents=True, exist_ok=True)
    with repairs_log.open("a", encoding="utf-8") as fh:
        fh.write("---\n")
        fh.write(yaml.dump(repair, default_flow_style=False, allow_unicode=True))


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------


def repair_feature_acs(
    feature_id: str,
    acceptance_criteria: list[str],
    auto_repair: bool = True,
    repairs_log: Path | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Detect smells in ACs, generate rewrites, apply ERROR-severity repairs.

    Returns::

        {
            "repaired_acs": list[str],          # ACs with repairs applied
            "repairs_applied": list[dict],      # repair records
            "smell_findings": list[SmellFinding],
        }

    When auto_repair=False, repaired_acs equals the original acceptance_criteria.
    """
    all_findings: list[SmellFinding] = []
    for ac in acceptance_criteria:
        findings = detect_all(
            ac,
            peer_criteria=[x for x in acceptance_criteria if x != ac],
            known_feature_ids=known_feature_ids,
        )
        all_findings.extend(findings)

    # Populate suggested_rewrite on all WARN/ERROR findings
    for finding in all_findings:
        if finding.severity in ("W", "E") and finding.suggested_rewrite is None:
            finding.suggested_rewrite = suggest_rewrite(finding)

    if not auto_repair:
        return {
            "repaired_acs": list(acceptance_criteria),
            "repairs_applied": [],
            "smell_findings": all_findings,
        }

    repairs_applied = apply_repairs(
        findings=all_findings,
        feature_id=feature_id,
        repairs_log=repairs_log,
        auto_repair=True,
    )

    # Build a map from original text → rewrite for quick lookup
    repair_map: dict[str, str] = {r["original"]: r["rewrite"] for r in repairs_applied}

    repaired_acs = [repair_map.get(ac, ac) for ac in acceptance_criteria]

    _update_metrics(repairs_applied, all_findings)

    return {
        "repaired_acs": repaired_acs,
        "repairs_applied": repairs_applied,
        "smell_findings": all_findings,
    }


# ---------------------------------------------------------------------------
# AC-required public API functions (F-a010e329 ACs)
# ---------------------------------------------------------------------------


class RewriteRejectedError(Exception):
    """Raised when the equivalence judge returns False for a rewrite."""


class EquivalenceJudgeUnavailableError(Exception):
    """Raised when the LLM judge is unreachable."""


def reject_unequivalent_rewrite(
    original: str,
    rewrite: str,
) -> str:
    """Raise RewriteRejectedError if rewrite is not semantically equivalent.

    Returns the rewrite string when equivalence passes.
    """
    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)
    if not is_equiv:
        raise RewriteRejectedError(
            f"Rewrite rejected (not equivalent): {rationale}"
        )
    return rewrite


def auto_apply_on_error_severity(
    finding: SmellFinding,
    rewrite: str,
) -> bool:
    """Apply rewrite only when smell severity is 'E' and equivalence passes.

    Returns True if the rewrite was applied, False otherwise.
    """
    if finding.severity != "E":
        return False
    is_equiv, _ = verify_semantic_equivalence(finding.text, rewrite)
    return is_equiv


def respect_opt_out(feature: Any) -> bool:  # noqa: ANN401
    """Return False when feature.auto_repair is False (opt-out).

    Accepts any object with an ``auto_repair`` attribute or dict with key ``auto_repair``.
    Returns True when auto_repair is not explicitly False.
    """
    if isinstance(feature, dict):
        return feature.get("auto_repair", True) is not False
    return getattr(feature, "auto_repair", True) is not False


def compute_auto_repair_rate() -> float:
    """Return float = applied / candidates over last 5 runs from metrics.yaml."""
    try:
        if not _METRICS_PATH.exists():
            return 0.0
        data = yaml.safe_load(_METRICS_PATH.read_text()) or {}
        history = data.get("auto_repair_history", [])[-5:]
        if not history:
            return 0.0
        return round(sum(r["rate"] for r in history) / len(history), 4)
    except Exception:
        return 0.0


def handle_missing_judge(original: str, rewrite: str) -> tuple[bool, str]:
    """Like verify_semantic_equivalence but raises EquivalenceJudgeUnavailableError on LLM failure.

    Raises EquivalenceJudgeUnavailableError when the judge LLM is unreachable.
    """
    prompt = _EQUIVALENCE_PROMPT_TEMPLATE.format(original=original, rewrite=rewrite)
    try:
        response = _call_llm_judge(prompt)
        text = response.content[0].text.strip() if response.content else ""
    except Exception as exc:
        raise EquivalenceJudgeUnavailableError(
            f"Equivalence judge LLM unreachable: {exc}"
        ) from exc
    return _parse_equivalence_response(text)


# ---------------------------------------------------------------------------
# Metrics tracking
# ---------------------------------------------------------------------------


def _update_metrics(repairs_applied: list[dict], all_findings: list[SmellFinding]) -> None:
    """Update auto_repair_rate in metrics.yaml."""
    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if _METRICS_PATH.exists():
            existing = yaml.safe_load(_METRICS_PATH.read_text()) or {}

        history = existing.get("auto_repair_history", [])
        error_findings = [f for f in all_findings if f.severity == "E"]
        run_rate = len(repairs_applied) / len(error_findings) if error_findings else 0.0
        history.append({"timestamp": datetime.now(timezone.utc).isoformat(), "rate": run_rate})
        # Keep last 5 runs for rate calculation
        history = history[-5:]

        avg_rate = sum(r["rate"] for r in history) / len(history) if history else 0.0
        existing["auto_repair_history"] = history
        existing["auto_repair_rate"] = round(avg_rate, 4)

        _METRICS_PATH.write_text(yaml.dump(existing, default_flow_style=False))
    except Exception as exc:
        logger.warning("Failed to update metrics.yaml: %s", exc)
