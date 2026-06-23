"""Auto-repair of smelly ACs with semantic-equivalence verification.

Linter-integrated module that:
  - Accepts SmellFinding objects from bob3.linter.detect_smells
  - Verifies rewrites via LLM semantic-equivalence judge
  - Auto-applies ERROR-severity rewrites that pass equivalence
  - Respects per-feature opt-out via auto_repair=False

Public API::

    from bob3.linter.auto_repair import apply_semantic_equivalence_check, should_auto_repair

    is_equiv, rationale = apply_semantic_equivalence_check(original, rewrite)

    repair = should_auto_repair(finding, auto_repair=True)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

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
    """Parse structured equivalence judge response."""
    equiv_match = re.search(r"EQUIVALENT:\s*(true|false)", text, re.IGNORECASE)
    rationale_match = re.search(r"RATIONALE:\s*(.+)", text, re.IGNORECASE)
    rationale = rationale_match.group(1).strip() if rationale_match else text
    if not equiv_match:
        return False, rationale or "Could not parse judge response"
    is_equiv = equiv_match.group(1).lower() == "true"
    return is_equiv, rationale


def apply_semantic_equivalence_check(
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
        (is_equivalent, rationale). On LLM failure returns (False, error_message).

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


def should_auto_repair(
    finding: Any,
    auto_repair: bool = True,
) -> bool:
    """Determine whether a smell finding qualifies for auto-repair.

    A finding qualifies when ALL of:
    - auto_repair is True (per-feature opt-out respected)
    - severity is ERROR ("E")
    - suggested_rewrite is not None

    Does NOT call the LLM; equivalence checking is a separate step.

    Parameters
    ----------
    finding:
        A SmellFinding (dataclass or dict) with at least ``severity`` and
        ``suggested_rewrite`` fields/keys.
    auto_repair:
        When False, always returns False (per-feature opt-out).

    Returns
    -------
    bool
        True if the finding should be submitted for equivalence check and applied.

    Raises
    ------
    ValueError
        If finding is None or lacks required fields.
    """
    if finding is None:
        raise ValueError("finding must not be None")

    if not auto_repair:
        return False

    if isinstance(finding, dict):
        severity = finding.get("severity")
        suggested_rewrite = finding.get("suggested_rewrite")
    elif hasattr(finding, "severity"):
        severity = finding.severity
        suggested_rewrite = getattr(finding, "suggested_rewrite", None)
    else:
        raise ValueError(
            f"finding must be a dict or object with severity attribute, got {type(finding).__name__}"
        )

    return severity == "E" and suggested_rewrite is not None
