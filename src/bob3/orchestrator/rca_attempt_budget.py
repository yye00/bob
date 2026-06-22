"""F-R7-479 extension: classify verification failures to grant fresh attempt budgets.

When the verification gate fails for a feature, the failure cause determines
whether the feature gets another attempt or is escalated to needs_human:

- ``code_emission_defect``: the emitted code is wrong but plausibly fixable by a
  different subagent attempt. Grant a fresh attempt if refinement_attempts < 5.
- ``spec_ambiguity``: the spec references symbols or behavior that no plausible
  code could satisfy. This is genuinely terminal — NH stands.
- ``infra_transient``: subprocess/IO/network error unrelated to the feature code.
  Always grant a fresh attempt (per existing F-R7-479 behavior).

The 5-attempt cap exists because verification failures are often code-fixable on
retry. Treating ALL non-infra verification failures as terminal defeats the budget.
"""

from __future__ import annotations

import re
from typing import Literal

Classification = Literal["code_emission_defect", "spec_ambiguity", "infra_transient"]

# Maximum refinement attempts before code_emission_defect is also terminal
_MAX_ATTEMPTS = 5

# AC prefixes that indicate behavior/integration/pytest work (code-fixable)
_CODE_FIXABLE_PREFIXES = (
    "behavior:",
    "integration:",
    "pytest:",
    "test:",
    "assert:",
)

# Patterns that indicate infrastructure / transient errors (unrelated to code)
_INFRA_PATTERNS = (
    r"subprocess\.CalledProcessError",
    r"subprocess\.TimeoutExpired",
    r"OSError",
    r"IOError",
    r"ConnectionRefusedError",
    r"ConnectionResetError",
    r"TimeoutError",
    r"self signed certificate",
    r"ECONNRESET",
    r"ETIMEDOUT",
    r"ENOTFOUND",
    r"ENOENT",
    r"502 Bad Gateway",
    r"503 Service Unavailable",
    r"504 Gateway Timeout",
    r"rate_limit_error",
    r"overloaded_error",
    r"APIStatusError.*529",
    r"APIConnectionError",
    r"net::ERR_",
)

_INFRA_REGEX = re.compile(
    "|".join(_INFRA_PATTERNS),
    re.IGNORECASE,
)


def classify_verification_failure(failed_acs: list[str]) -> Classification:
    """Classify why verification gate failed.

    Parameters
    ----------
    failed_acs:
        List of AC strings (or error messages) that caused verification to fail.

    Returns
    -------
    ``"infra_transient"``   if any AC text matches an infrastructure error pattern.
    ``"code_emission_defect"`` if any AC starts with a behavior/integration/pytest prefix.
    ``"spec_ambiguity"``    otherwise (including empty list).
    """
    if not failed_acs:
        return "spec_ambiguity"

    for ac in failed_acs:
        if _INFRA_REGEX.search(ac):
            return "infra_transient"

    for ac in failed_acs:
        ac_lower = ac.lower().strip()
        for prefix in _CODE_FIXABLE_PREFIXES:
            if ac_lower.startswith(prefix):
                return "code_emission_defect"

    return "spec_ambiguity"


def should_grant_fresh_attempt(
    classification: Classification,
    refinement_attempts: int,
) -> bool:
    """Return True if the feature should receive another attempt budget.

    Rules:
    - ``"code_emission_defect"``: grant if refinement_attempts < _MAX_ATTEMPTS.
    - ``"infra_transient"``: always grant (existing F-R7-479 behavior).
    - ``"spec_ambiguity"``: never grant (genuinely terminal).
    - Unknown classifications: return False (safe default).
    """
    if classification == "infra_transient":
        return True
    if classification == "code_emission_defect":
        return refinement_attempts < _MAX_ATTEMPTS
    # spec_ambiguity or anything unrecognized
    return False
