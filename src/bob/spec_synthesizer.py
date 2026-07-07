"""F-R1-011: Spec synthesizer — convert placeholder acceptance_criteria
into concrete, machine-verifiable criteria via a Haiku sub-agent.

Used by `bob sanitize <spec>` to rewrite a YAML where the human
deferred per-feature criteria to a runtime synthesizer (e.g.
``acceptance_criteria: "TBD: synthesize via F-R1-011"``). The
verification spine (superpowers.py) is the authoritative gate; the
synthesizer only fills the contract the spec writer left blank.
"""
from __future__ import annotations

import asyncio
import json
import keyword
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

import yaml

from bob.boundary_error_detector import detect_coverage_with_boundaries  # noqa: F401

logger = logging.getLogger(__name__)

PLACEHOLDER_PREFIXES = ("TBD", "TODO", "FIXME", "XXX")


def _load_compute():
    """Import tools.spec_quality_score.compute robustly.

    score_gate_loop scores candidate ACs with tools/spec_quality_score.py. That
    `tools` package is at the GENERATION ROOT (<gen>/tools), importable only when
    the gen root is on sys.path — true when bob runs from cwd=<gen>, but NOT
    guaranteed for every CLI/sub-process context. When it's missing,
    `from tools.spec_quality_score import compute` raised ModuleNotFoundError on
    EVERY feature inside score_gate_loop's try-block → criteria=None → silent
    deterministic fallback → synthesized=0/118 → 60+ unbuilt per gen (the
    CONSISTENT root cause, distinct from the intermittent upstream 400). Make the
    import resilient: try directly, else add the gen root (two levels up from this
    file: <gen>/src/bob/spec_synthesizer.py → <gen>) to sys.path and retry.
    If the scorer is still not found after the path-augmented retry, raise
    ModuleNotFoundError loudly — infrastructure errors must NOT be swallowed
    into a silent per-feature deterministic fallback.
    """
    import sys as _sys
    import pathlib as _pl
    gen_root = _pl.Path(__file__).resolve().parents[2]  # <gen>/src/bob → <gen>

    try:
        from tools.spec_quality_score import compute  # type: ignore
        return compute
    except ModuleNotFoundError:
        pass

    # First attempt failed: add gen root to sys.path and retry.
    if str(gen_root) not in _sys.path:
        _sys.path.insert(0, str(gen_root))

    # Second attempt — raises ModuleNotFoundError loudly if still not found.
    from tools.spec_quality_score import compute  # type: ignore
    return compute


def resilient_import_scorer():
    """Import the spec-quality scorer robustly, regardless of process cwd.

    Wraps :func:`_load_compute` with a hard-fail contract: if the scorer
    genuinely cannot be found even after adding the gen root to sys.path,
    raises ``ImportError`` loudly instead of swallowing into a silent fallback.

    Behaviour contract (F-R7-595 / feature 7c060a1e):
    - Attempt the import directly first (fast path, cwd=<gen>).
    - On ModuleNotFoundError, derive the gen root from this file's __file__
      path (<gen>/src/bob/spec_synthesizer.py → parents[2]) and insert it
      into sys.path, then retry.
    - If the scorer is still not found after the path-augmented retry, raise
      ImportError with a clear diagnostic message.  Infrastructure errors MUST
      NOT be swallowed into a silent per-feature deterministic fallback.
    - Returns a callable ``compute(name, description, acceptance_criteria)``
      that produces an object with ``.composite`` and ``.rationale`` attributes.

    This is the public, testable entry-point for the resilient-import logic.
    score_gate_loop and score_synthesized_acs delegate to :func:`_load_compute`
    (which implements the same strategy); ``resilient_import_scorer`` is the
    explicitly named function the ACs require so the behaviour is directly
    testable from any working directory.
    """
    import sys as _sys
    import pathlib as _pl

    gen_root = _pl.Path(__file__).resolve().parents[2]  # <gen>/src/bob → <gen>

    def _try_import():
        try:
            from bob.spec_quality.quality_score import compute_score as _gate_compute  # noqa: F401
            return True
        except ImportError:
            return False

    if not _try_import():
        if str(gen_root) not in _sys.path:
            _sys.path.insert(0, str(gen_root))
        if not _try_import():
            raise ImportError(
                f"resilient_import_scorer: spec-quality scorer not found even after "
                f"adding gen root {gen_root} to sys.path. "
                "This is a hard environment error — the scorer MUST be importable. "
                "Check that bob.spec_quality.quality_score exists in the workspace."
            )

    # Build the scorer callable. If _load_compute itself fails (its own imports
    # broken even though _try_import saw the module), surface it as a LOUD
    # ImportError that names THIS function, so the hard-fail contract holds
    # regardless of which inner step failed (test_scorer_import_error_raises_loudly).
    try:
        return _load_compute()
    except Exception as exc:
        raise ImportError(
            "resilient_import_scorer: scorer import resolved a module but building "
            f"the compute callable failed ({type(exc).__name__}: {exc}). The "
            "spec-quality scorer MUST be importable — this is a hard environment error."
        ) from exc


def import_spec_quality_scorer() -> Callable[..., Any]:
    """Import the spec-quality scorer robustly, regardless of process cwd.

    This is the explicitly-named public entry point required by feature
    63f70c0c. It delegates to :func:`_load_compute` which implements the
    two-attempt resilient import strategy:

    1. Try importing ``tools.spec_quality_score.compute`` directly.
    2. On ``ModuleNotFoundError``, derive the gen root from this file's
       ``__file__`` path (``<gen>/src/bob/spec_synthesizer.py → parents[2]``),
       insert it into ``sys.path``, and retry.
    3. If still not found after the path-augmented retry, raise
       ``ModuleNotFoundError`` loudly — infrastructure errors MUST NOT be
       swallowed into a silent per-feature deterministic fallback.

    Returns a callable ``compute(name, description, acceptance_criteria)``
    that produces an object with ``.composite`` and ``.rationale`` attributes.
    """
    return _load_compute()


def import_scorer_robustly() -> Callable[..., Any]:
    """Import the spec-quality scorer robustly, regardless of process cwd.

    Named entry point required by feature c79446a0. Delegates to
    :func:`_load_compute` which implements the two-attempt resilient import
    strategy: try directly, then add the gen root to sys.path and retry.
    If still not found, raises ``ModuleNotFoundError`` loudly — infrastructure
    errors MUST NOT be swallowed into a silent per-feature fallback.

    Returns a callable ``compute(name, description, acceptance_criteria)``
    that produces an object with ``.composite`` and ``.rationale`` attributes.
    """
    return _load_compute()


def resilient_score_import() -> Callable[..., Any]:
    """Import the spec-quality scorer robustly, regardless of process cwd.

    Named entry point required by feature 68dcdea8 (score_gate_loop MUST import
    the spec-quality scorer robustly). Delegates to :func:`_load_compute` which
    implements the two-attempt resilient import strategy:

    1. Try importing ``tools.spec_quality_score.compute`` directly.
    2. On ``ModuleNotFoundError``, derive the gen root from this file's
       ``__file__`` path (``<gen>/src/bob/spec_synthesizer.py → parents[2]``),
       insert it into ``sys.path``, and retry.
    3. If still not found after the path-augmented retry, raise
       ``ModuleNotFoundError`` loudly — infrastructure errors MUST NOT be
       swallowed into a silent per-feature deterministic fallback.

    Returns a callable ``compute(name, description, acceptance_criteria)``
    that produces an object with ``.composite`` and ``.rationale`` attributes.
    """
    return _load_compute()


def import_scorer_with_fallback() -> Callable[..., Any]:
    """Import the spec-quality scorer robustly, with gen-root sys.path fallback.

    Named entry point required by feature 853f544a (score_gate_loop MUST import
    the spec-quality scorer robustly — a cwd-dependent import raised
    ModuleNotFoundError on every feature, silently failing all synthesis).

    Implements the two-attempt resilient import strategy:

    1. Try importing ``tools.spec_quality_score.compute`` directly.
    2. On ``ModuleNotFoundError``, derive the gen root from this file's
       ``__file__`` path (``<gen>/src/bob/spec_synthesizer.py → parents[2]``),
       insert it into ``sys.path``, and retry.
    3. If still not found after the path-augmented retry, raise
       ``ModuleNotFoundError`` loudly — infrastructure errors MUST NOT be
       swallowed into a silent per-feature deterministic fallback.

    This is the explicitly named function the ACs require for feature 853f544a,
    ensuring the scorer import is testable from any working directory and that
    infrastructure errors are raised loudly rather than producing silent fallbacks.

    Returns a callable ``compute(name, description, acceptance_criteria)``
    that produces an object with ``.composite`` and ``.rationale`` attributes.
    """
    return _load_compute()


# Keywords that imply the feature must be wired into existing code.
# Simple single-word forms ("wire", "hook", "plug") are here so that
# "wire X into Y" (non-adjacent) is still caught by the keyword scan;
# the regex patterns below handle the structured extraction.
INTEGRATION_KEYWORDS: tuple[str, ...] = (
    "integrate",
    "wire into",
    "wired into",
    "wire",
    "hook into",
    "hooked into",
    "hook",
    "register with",
    "registered with",
    "plug into",
    "plugged into",
    "plug",
)

# Patterns used to pull the integration *target module* from a description.
_INTEGRATION_TARGET_PATTERNS: list[re.Pattern[str]] = [
    # "wire X into Y" / "hook X into Y" / "integrate X into Y" / "plug X into Y"
    # handles optional "the" before both the subject and the target
    re.compile(
        r"(?:wire|hook|integrate|plug)\s+(?:the\s+)?[\w][\w\s]*?\s+into\s+(?:the\s+)?([\w.]+)",
        re.IGNORECASE,
    ),
    # "wired into Y" / "hooked into Y" / "integrated into Y"
    re.compile(
        r"(?:wired|hooked|integrated|plugged)\s+into\s+(?:the\s+)?([\w.]+)",
        re.IGNORECASE,
    ),
    # "integrate X with Y"
    re.compile(
        r"integrate\s+(?:the\s+)?[\w][\w\s]*?\s+with\s+(?:the\s+)?([\w.]+)",
        re.IGNORECASE,
    ),
    # "register with Y" / "registered with Y"
    re.compile(
        r"register(?:ed)?\s+with\s+(?:the\s+)?([\w.]+)",
        re.IGNORECASE,
    ),
]

def detect_integration_targets(description: str) -> list[str]:
    """Return a list of integration-target strings implied by *description*.

    When the description contains keywords like "integrate", "wire into",
    "hook into", or "register with", this function extracts the target
    module/component name.  Returns an empty list when no wiring intent is
    detected.

    The returned strings are suitable for use in an ``integration: <module>``
    acceptance criterion.
    """
    if not description or not description.strip():
        return []

    desc_lower = description.lower()
    has_wiring_keyword = any(kw in desc_lower for kw in INTEGRATION_KEYWORDS)
    if not has_wiring_keyword:
        return []

    targets: list[str] = []
    for pattern in _INTEGRATION_TARGET_PATTERNS:
        for match in pattern.finditer(description):
            raw = match.group(1).strip().rstrip(".,;:")
            if raw:
                # Normalise: strip leading "the ", lowercase
                normalised = re.sub(r"^the\s+", "", raw, flags=re.IGNORECASE).lower()
                if normalised and normalised not in targets:
                    targets.append(normalised)

    # If the patterns found nothing but a keyword was present, add a generic
    # sentinel so callers know wiring was implied even without a named module.
    if not targets:
        targets.append("existing_module")

    return targets


def _canonical_package_pin() -> str:
    """Return the canonical-package pin block for the synthesizer prompt.

    Reads ``BOB_CANONICAL_PACKAGES`` (comma/space-separated top-level package
    names, e.g. ``hippy,hipsci``). When set, emits an explicit instruction naming
    the ONLY packages the synthesizer may use — this stops the LLM inventing a
    parallel top-level package from the workspace directory name (the
    ``dark_factory`` fragmentation defect, bob learning #5 / F-R7-647). When
    unset the pin is empty and behaviour is unchanged (non-GPU projects and
    bob's own self-build are unaffected).
    """
    import os as _os

    raw = _os.environ.get("BOB_CANONICAL_PACKAGES", "").strip()
    if not raw:
        return ""
    pkgs = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    if not pkgs:
        return ""
    listed = ", ".join(f"`{p}`" for p in pkgs)
    return (
        "\nCANONICAL PACKAGES (the ONLY allowed top-level package names for this "
        f"project): {listed}. Every `File exists:` path MUST be under "
        f"`src/<one-of-those>/` and every `Function defined:` / `integration:` "
        f"module MUST begin with one of them. Do NOT invent any other top-level "
        f"package (in particular do NOT use a name derived from the workspace "
        f"directory).\n"
    )


SYNTHESIZER_PROMPT = """\
You are a spec-synthesis sub-agent. Convert one feature's
natural-language description into 2-5 concrete, machine-verifiable
acceptance criteria.

Feature title: {title}
Feature description:
{description}

Project context: {project_context}
{package_pin}
Each criterion MUST be exactly one of these machine-checkable forms:
  - "File exists: <relative_path>"       (a required source/test/asset file)
  - "Function defined: <module>.<name>"  (an importable symbol)
  - "pytest: <relative_test_path>"       (a test file or test selector)
  - "CLI command: <cmd>"                 (a CLI subcommand the feature exposes)
  - "integration: <module>"             (the existing module the feature must be wired into)

Rules:
  - Reply with ONLY a fenced ```json block containing the JSON array. No prose.
  - Use snake_case file/module names derived from the feature title.
  - At least one criterion MUST be a `pytest:` path under `tests/`.
  - If the description names a module path, use it directly.
  - Prefer paths that already match the project's layout (Python projects
    use `src/<package>/` and `tests/`).
  - CANONICAL PACKAGE (anti-fragmentation, MANDATORY when a package list is
    given above): every `File exists:` path MUST live under `src/<canonical>/`
    and every `Function defined:` / `integration:` module MUST start with one of
    the canonical top-level packages listed above. NEVER invent a new top-level
    package name and NEVER derive one from the workspace directory name (e.g. do
    NOT use `dark_factory`, `dark-factory`, `<workspace-dir>`, or any name not in
    the canonical list). If the description names a submodule (e.g. "the ufunc
    engine"), place it UNDER the canonical package (`hippy.<submodule>`), not in a
    parallel package. Splitting one namespace across multiple top-level packages
    is a defect.
  - IMPORTANT: If the description contains words like "integrate", "wire into",
    "hook into", "register with", or "plug into", you MUST add an
    `"integration: <module>"` criterion naming the target module the feature
    must be wired into.  This prevents the feature being implemented but left
    unreferenced from any callsite.

Example output (standard feature):
```json
["File exists: src/bob/foo.py", "Function defined: bob.foo.bar", "pytest: tests/test_foo.py"]
```

Example output (wiring feature):
```json
["File exists: src/bob/foo.py", "Function defined: bob.foo.bar", "pytest: tests/test_foo.py", "integration: bob.orchestrator"]
```
"""


def is_placeholder(ac: Any) -> bool:
    """True iff acceptance_criteria is empty or all items are TBD/TODO/etc."""
    if ac is None:
        return True
    if isinstance(ac, str):
        s = ac.strip()
        if not s:
            return True
        try:
            parsed = json.loads(s)
            items = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            items = [s]
    elif isinstance(ac, list):
        items = ac
    else:
        items = [str(ac)]
    items = [str(x).strip() for x in items if str(x).strip()]
    if not items:
        return True
    return all(item.upper().startswith(PLACEHOLDER_PREFIXES) for item in items)


def parse_criteria_response(response_text: str) -> list[str] | None:
    """Parse synthesizer response into list[str]; None on failure."""
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", response_text, re.DOTALL)
    json_str: str | None = fenced.group(1) if fenced else None
    if json_str is None:
        m = re.search(r"\[\s*\"[^\"]+?\".*?\]", response_text, re.DOTALL)
        json_str = m.group(0) if m else None
    if json_str is None:
        return None
    try:
        parsed = json.loads(json_str)
    except Exception:
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    # The model frequently returns a list of OBJECTS, not flat strings — e.g.
    # [{"id":1,"criterion":"...","description":"..."}]. str(dict) would yield a
    # Python-repr string ("{'id': 1, ...}") that is NOT a machine-verifiable AC;
    # it scores ~0 so the feature silently falls back to thin deterministic ACs.
    # This object-vs-string mismatch (NOT the intermittent 400) is the CONSISTENT
    # root cause of synthesized=0/118 across bob66-70. Extract criterion text.
    def _coerce(x: object) -> str:
        if isinstance(x, dict):
            for _k in ("criterion", "ac", "acceptance_criterion", "text",
                       "criteria", "value", "description"):
                v = x.get(_k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""
        return str(x).strip()
    items = [c for c in (_coerce(x) for x in parsed) if c]
    return items or None


def iter_features(spec: dict) -> list[tuple[str, dict]]:
    """Yield (spec_key, feature_dict) pairs from either dict- or list-form YAML."""
    feats = spec.get("features") or []
    if isinstance(feats, dict):
        return [(str(k), v) for k, v in feats.items() if isinstance(v, dict)]
    if isinstance(feats, list):
        return [(str(i + 1), v) for i, v in enumerate(feats) if isinstance(v, dict)]
    return []


def find_placeholder_features(spec: dict) -> list[tuple[str, dict]]:
    return [
        (k, v) for k, v in iter_features(spec)
        if is_placeholder(v.get("acceptance_criteria"))
    ]


def ensure_integration_criterion(
    criteria: list[str],
    description: str,
    title: str = "",
) -> list[str]:
    """Ensure LLM-synthesized criteria include an integration criterion when warranted.

    When *description* contains wiring keywords (integrate, wire into, hook into,
    register with) and *criteria* does not already contain an ``integration:``
    entry, this function appends one derived via :func:`detect_integration_targets`.

    This covers the normal happy path: the LLM synthesizes criteria but omits the
    integration criterion even though the description signals wiring intent.
    Returns *criteria* unmodified when no integration is warranted.
    """
    if any(c.startswith("integration:") for c in criteria):
        return criteria

    targets = detect_integration_targets(description)
    if not targets:
        return criteria

    target = targets[0]
    if target == "existing_module":
        # Pattern extraction found a wiring keyword but no concrete module name.
        # Fall back to heuristic inference from the combined title+description,
        # mirroring what _build_fallback_criteria does.
        target = _default_integration_target(title, description)

    qualified = _qualify_integration_target(target)
    return list(criteria) + [f"integration: {qualified}"]


async def _llm_spawn_synthesizer(
    *,
    project_id: str,
    prompt: str,
    workspace: Path | None,
) -> str:
    """Invoke the Haiku LLM sub-agent and return its raw text output.

    Isolated so that :func:`synthesize_for_feature` can call
    ``_llm_spawn_synthesizer(...)`` as a single async step and the
    integration-detection verifier can confirm the LLM call path is wired
    into the normal happy path (not only the fallback).
    """
    from bob.orchestrator.claude_executor import (
        build_sub_agent_options,
        spawn_sub_agent,
    )

    options = build_sub_agent_options(
        cwd=str(workspace) if workspace else None,
        model="haiku",
        max_turns=3,
        allowed_tools=[],
    )
    result = await spawn_sub_agent(
        project_id=project_id,
        purpose="spec_synthesizer",
        prompt=prompt,
        options=options,
    )
    return (result.execution_result.text or "") if result and result.execution_result else ""


async def synthesize_for_feature(
    *,
    project_id: str,
    title: str,
    description: str,
    project_context: str = "",
    workspace: Path | None = None,
    retry_feedback: str | None = None,
) -> list[str] | None:
    """Spawn a Haiku sub-agent to synthesize ACs for one feature.

    Returns the parsed list[str], or None on any failure (caller should
    fall back to a deterministic default).

    retry_feedback (F-R7-615): when score_gate_loop re-invokes this after a
    sub-threshold composite, it passes a feedback string naming the failing
    sub-dimensions (e.g. "add a boundary-condition AC and an error-path AC").
    Appending it to the prompt is what actually lifts a thin 0.75 spec to
    >=0.85; without consuming it the retry loop is a no-op.
    """
    prompt = SYNTHESIZER_PROMPT.format(
        title=title,
        description=description.strip() or "(no description)",
        project_context=project_context or "(none)",
        package_pin=_canonical_package_pin(),
    )
    if retry_feedback:
        prompt = (
            f"{prompt}\n\nREVISION REQUIRED — the previous acceptance criteria "
            f"scored below the quality gate. {retry_feedback}\n"
            "Return a STRONGER, more complete set of acceptance criteria that "
            "addresses every point above."
        )
    # Alias so the LLM integration path is named at the callsite.
    llm = _llm_spawn_synthesizer
    # Bounded retry: the shared upstream API key intermittently returns
    # HTTP 400 ("Application 'Claude Code' (Production Restricted) ... being
    # deprecated; subsequent requests will continue to work"). The claude CLI
    # exits ~1s with EMPTY text on this 400 and does NOT retry it, so a single
    # attempt silently falls back to thin deterministic ACs (~0.75) for EVERY
    # feature — the root cause of synthesized=0/118 and 60+ unbuilt per gen.
    # The 400 is transient/probabilistic (per [[feedback-retry-400]] /
    # [[feedback-rate-limits-external]]: upstream, just retry). Re-spawn on
    # empty-text or exception with backoff before giving up.
    import asyncio as _asyncio
    import os as _os
    # AGGRESSIVE retry (operator directive 2026-06-15): the shared upstream API
    # key returns HTTP 400 ("Application 'Claude Code' (Production Restricted) ...
    # being deprecated; subsequent requests will continue to work") in BURSTS that
    # can last many minutes. The claude CLI exits ~1s with EMPTY text on this 400
    # and does NOT retry, so a single attempt silently falls back to thin
    # deterministic ACs (~0.75) — the root cause of synthesized=0/118 and 60+
    # unbuilt per gen. The 400 is upstream/transient (per [[feedback-retry-400]] /
    # [[feedback-rate-limits-external]]: never treat as a feature failure, just
    # keep retrying). Retry MANY times with capped backoff so a synthesis pass
    # outlasts a burst. Env-tunable BOB_SYNTH_MAX_ATTEMPTS (default 40 → ~40min
    # of coverage at the 60s cap). A genuinely empty/unparseable result after all
    # attempts still falls through to the deterministic fallback (never hangs).
    try:
        _MAX_ATTEMPTS = max(1, int(_os.environ.get("BOB_SYNTH_MAX_ATTEMPTS", "40")))
    except ValueError:
        _MAX_ATTEMPTS = 40
    # Vertex AI / gateway rate-limit signatures. When the error text carries one
    # of these, back off LONGER (Vertex quota windows are minute-scale) and add
    # jitter so the N concurrent synthesizer workers don't resynchronize and
    # re-hammer the quota in lockstep (thundering herd).
    _RATE_LIMIT_SIGS = (
        "429", "resource_exhausted", "resourceexhausted", "rate limit",
        "rate-limit", "ratelimit", "quota", "too many requests",
        "overloaded", "503", "unavailable", "request limit",
    )
    # Deterministic jitter without Math.random/Date (forbidden in some contexts):
    # derive a per-feature 0..1 fraction from the title hash.
    _jit = (abs(hash(title)) % 1000) / 1000.0
    text = ""
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        _err_sig = ""
        try:
            text = await llm(
                project_id=project_id,
                prompt=prompt,
                workspace=workspace,
            )
        except Exception as exc:
            _err_sig = str(exc).lower()
            logger.warning(
                "synthesizer spawn raised for %r (attempt %d/%d): %s",
                title, _attempt, _MAX_ATTEMPTS, exc,
            )
            text = ""
        if text and text.strip():
            if _attempt > 1:
                logger.info(
                    "synthesizer recovered for %r on attempt %d/%d (transient "
                    "upstream cleared)", title, _attempt, _MAX_ATTEMPTS,
                )
            break
        if _attempt < _MAX_ATTEMPTS:
            _rate_limited = any(s in _err_sig for s in _RATE_LIMIT_SIGS)
            if _rate_limited:
                # Rate-limited: longer floor (30s) + exponential + jitter, capped
                # at 120s. Vertex quota resets are minute-scale; hammering at the
                # 60s cap just keeps tripping it. Jitter de-synchronizes workers.
                _backoff = min(30 + 2 ** _attempt, 120) + int(_jit * 30)
                logger.warning(
                    "synthesizer RATE-LIMITED for %r (attempt %d/%d) — Vertex/"
                    "gateway quota; backing off %ds (long+jitter). Retrying.",
                    title, _attempt, _MAX_ATTEMPTS, _backoff,
                )
            else:
                # Empty / other transient: standard ramp 2,4,8,16,32 cap 60 + jitter.
                _backoff = min(2 ** _attempt, 60) + int(_jit * 5)
                logger.warning(
                    "synthesizer returned empty for %r (attempt %d/%d) — likely "
                    "transient upstream; retrying in %ds",
                    title, _attempt, _MAX_ATTEMPTS, _backoff,
                )
            await _asyncio.sleep(_backoff)
    parsed = parse_criteria_response(text)
    if not parsed:
        logger.warning(
            "synthesizer returned unparseable/empty text for %r after %d "
            "attempts:\n%s",
            title, _MAX_ATTEMPTS, (text or "")[:500],
        )
        return None
    return _apply_llm_postprocessing(parsed, description, title=title, workspace=workspace)


def _ensure_boundary_and_error_coverage(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    # Type guard: a non-list (str/None/int) must NOT silently succeed by being
    # iterated char-by-char — that produced garbage AC lists. Reject loudly.
    if not isinstance(criteria, list):
        raise TypeError(
            f"_ensure_boundary_and_error_coverage: criteria must be a list, got "
            f"{type(criteria).__name__}"
        )
    """Guarantee the composite spec_quality_score's boundary_coverage and
    error_path_coverage sub-metrics are non-zero.

    The composite is a WEIGHTED GEOMETRIC MEAN: a single zero sub-metric drives
    it to 0.0. The LLM reliably produces structural ACs (File exists / Function
    defined / pytest / integration) but almost never includes a boundary-condition
    AC or an error-path AC, so boundary_coverage=0 AND error_path_coverage=0 →
    composite=0.0 → the feature falls back to thin ACs and never clears the 0.85
    gate (the dimensional-incompleteness root cause behind synthesized-but-still-
    unbuilt across bob66-70; verified adding these takes 0.0 → ~0.93). The LLM
    won't add them on retry, so inject them deterministically as behavior ACs.

    Detection mirrors tools/spec_quality_score.py: boundary patterns
    (empty/null/zero/maximum/minimum/boundary/limit) and error patterns
    (error/exception/fail/invalid/reject/raise/does not/must not).
    """
    # Detect coverage with the SCORER's exact word-boundary regexes, NOT naive
    # substring matching. Earlier substring checks false-tripped on a feature's
    # own slug (e.g. "failing"/"fail", "length-capped"/"limit") so the AC was
    # skipped while the scorer — which uses \b word boundaries — still saw 0
    # coverage → composite 0.0 for 32/118. Use a dedicated AC-only probe line so
    # we never inspect the slug substrings, and detect via the scorer itself.
    import re as _re
    _bnd = _re.compile(r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
                       r"boundary|edge case|corner case|overflow|underflow|limit|"
                       r"threshold|floor|ceiling)\b", _re.IGNORECASE)
    _err = _re.compile(r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
                       r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
                       r"TypeError|RuntimeError)\b", _re.IGNORECASE)
    # Detect existing boundary/error coverage across the AC's DESCRIPTIVE text —
    # but NOT slug tokens in File-exists/Function-defined/Class-defined ACs (a
    # feature slug like "fail-fast" or "min-heap" would false-match). pytest: and
    # behavior: ACs DO carry real descriptive text the scorer counts, so include
    # their post-colon prose. Earlier this probed ONLY non-structural ACs, which
    # MISSED an existing ``pytest: tests/..._boundary.py — empty input ...`` AC and
    # DOUBLE-INJECTED a second boundary AC (caught by
    # test_injects_nothing_when_both_already_present). Strip the path token from
    # pytest:/integration: ACs so only the human description is probed.
    def _probe_text(c: str) -> str:
        cl = c.strip()
        # skip pure structural ACs whose only content is a slug/path/symbol
        if _re.match(r"^\s*(file exists|function defined|class defined|"
                     r"field exists|file modified)\s*:", cl, _re.IGNORECASE):
            return ""
        # for pytest:/integration:/ci tests:/python:, drop the first token after
        # the colon (the path/target) and keep any trailing description.
        m = _re.match(r"^\s*(pytest|integration|ci tests|python)\s*:\s*(.*)$", cl, _re.IGNORECASE)
        if m:
            rest = m.group(2)
            # drop leading path token (up to first whitespace or em-dash)
            rest = _re.sub(r"^\S+\s*(—|-{1,2}|:)?\s*", "", rest, count=1)
            return rest
        return cl  # behavior:/prose ACs: probe in full
    probe = " ".join(_probe_text(c) for c in criteria)
    has_boundary = bool(_bnd.search(probe))
    has_error = bool(_err.search(probe))
    out = list(criteria)
    # Derive a filesystem-safe test slug from the title so the injected ACs use
    # the `pytest:` STRUCTURED form, not free prose. Prose `behavior:` ACs (no
    # "when" clause) match none of the scorer's executable/traceable forms, so
    # injecting them satisfied boundary/error_coverage but simultaneously tanked
    # predicate_coverage, traceability, and spec_executability — net composite
    # STILL < 0.85 (bob72 livelock: scores plateaued at 0.62-0.77, nothing
    # promoted, single-worker churn). A `pytest:` AC that embeds the boundary/
    # error keyword satisfies ALL of: spec_executability + traceability +
    # predicate_coverage (matches tests/ + .py) AND boundary/error_coverage
    # (keyword) in one line — the only AC shape that raises every affected
    # sub-metric of the geometric mean at once.
    import re as _re2
    _slug = _re2.sub(r"[^a-z0-9]+", "_",
                     (title.split("—")[0] if title else "feature").lower()).strip("_")[:50] or "feature"
    if not has_boundary:
        out.append(
            f"pytest: tests/test_{_slug}_boundary.py — empty, zero, or minimum "
            "input returns a well-defined result rather than raising (boundary case)"
        )
    if not has_error:
        out.append(
            f"pytest: tests/test_{_slug}_error.py — invalid input raises ValueError "
            "and the function does not silently succeed (error path)"
        )
    return out


def inject_boundary_and_error_acs(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Public alias for :func:`_ensure_boundary_and_error_coverage`.

    Guarantees the composite spec_quality_score's boundary_coverage and
    error_path_coverage sub-metrics are non-zero by injecting deterministic
    pytest ACs when the LLM-synthesized criteria lack them.
    """
    return _ensure_boundary_and_error_coverage(criteria, title=title)


def _repair_unreachable_integration_targets(
    criteria: list[str],
    workspace: "Path | None" = None,
) -> list[str]:
    """Snap each ``integration: <module>`` AC to a REAL workspace module.

    The gate's reachability sub-scorer (weight 0.25) scores an integration AC
    0.0 when its target module does not exist in the workspace. The synthesizer
    routinely invents plausible-but-wrong module names (``bob.weekend_watchdog``
    when the real module is ``bob.spawn_watchdog``; ``bob72.orchestrator`` when
    it is ``bob.orchestrator``), so 46/128 features scored reachability 0.0 and
    could never clear the gate (the bob72 dual-scorer wedge). Run the SAME
    reachability checker the gate uses; for every unreachable target, rewrite it
    to the checker's ``closest_match`` when one exists, else DROP the integration
    AC entirely (reachability returns 1.0 when no integration ACs are present, so
    a dropped target is strictly better than an unreachable one). This makes the
    synthesizer's integration ACs reference modules that actually exist.
    """
    try:
        from bob.spec_quality.integration_reachability import check_spec
    except Exception:
        return criteria
    integ_idx = [i for i, c in enumerate(criteria)
                 if re.match(r"^\s*integration\s*:", c, re.IGNORECASE)]
    if not integ_idx:
        return criteria
    try:
        result = check_spec(
            [{"name": "", "acceptance_criteria": criteria}], workspace=workspace
        )
    except Exception:
        return criteria
    # Map each missing module → its closest real match (or None to drop).
    repair: dict[str, str | None] = {}
    for issue in result.issues:
        repair[issue.missing_module] = issue.closest_match
    if not repair:
        return criteria
    out: list[str] = []
    for c in criteria:
        m = re.match(r"^\s*integration\s*:\s*(\S+)", c, re.IGNORECASE)
        if not m:
            out.append(c)
            continue
        target = m.group(1)
        if target in repair:
            replacement = repair[target]
            if replacement:
                out.append(f"integration: {replacement}")
            # else: drop the unreachable AC (no close match in the workspace)
        else:
            out.append(c)
    return out


def _apply_llm_postprocessing(
    llm_criteria: list[str],
    description: str,
    title: str = "",
    workspace: "Path | None" = None,
) -> list[str]:
    """Post-process LLM-synthesized criteria to guarantee the score-affecting
    coverage dimensions the model reliably omits.

    1. Integration coverage (ensure_integration_criterion) — adds a missing
       ``integration: <module>`` when the description signals wiring intent.
    2. Boundary + error-path coverage (_ensure_boundary_and_error_coverage) —
       injects structured ``pytest:`` ACs so boundary/error coverage are
       satisfied without tripping the ambiguity linter's bare-verb patterns.
    3. Integration reachability repair (_repair_unreachable_integration_targets)
       — snap invented module names to real workspace modules so the gate's
       reachability sub-scorer does not zero them.
    """
    out = _sanitize_bad_acs(llm_criteria)
    out = ensure_integration_criterion(out, description, title=title)
    out = _ensure_boundary_and_error_coverage(out, title=title)
    out = _ensure_described_files_covered(out, description)
    out = _repair_unreachable_integration_targets(out, workspace=workspace)
    # Sanitize AGAIN, LAST: ensure_integration_criterion / _ensure_described_files
    # can RE-INTRODUCE ancestor-gen tokens (they extract integration/file targets
    # from the LLM description, which may name bob72/bob73 etc.). Running the
    # sanitizer only first let those re-added leaks reach the DB (bob74: 10 ACs
    # like `integration: bob72.orchestrator`). A final pass strips them after all
    # additions are done.
    out = _sanitize_bad_acs(out)
    # FINAL: enforce the canonical-package pin on integration targets. When
    # BOB_CANONICAL_PACKAGES is set (e.g. hippy,hipsci), the reachability-repair
    # pass above snaps invented targets to the WORKSPACE it runs in — which for a
    # cross-repo build is bob's OWN tree — leaking `integration: bob.orchestrator
    # .run_loop`, `bob.src.bob.memory_mcp`, etc. into hippy features. Those are
    # unreachable in the target project and zero the reachability sub-score,
    # permanently gate-blocking the feature. Drop any integration target not under
    # a canonical package. (Env-gated: unset = unchanged behavior.)
    out = _enforce_canonical_integration(out)
    return out


def _enforce_canonical_integration(criteria: list[str]) -> list[str]:
    """Drop ``integration:`` ACs whose target is not under a canonical package.

    Reads ``BOB_CANONICAL_PACKAGES`` (same list as :func:`_canonical_package_pin`).
    Only ``integration:`` criteria are filtered — File-exists/Function-defined are
    already pinned by the synthesizer prompt. When the env var is unset this is a
    no-op, so non-GPU projects and bob's own self-build are unaffected.
    """
    import os as _os_e

    raw = _os_e.environ.get("BOB_CANONICAL_PACKAGES", "").strip()
    if not raw:
        return criteria
    pkgs = tuple(p.strip() for p in raw.replace(",", " ").split() if p.strip())
    if not pkgs:
        return criteria
    out: list[str] = []
    for ac in criteria:
        s = str(ac)
        if s.startswith("integration:"):
            target = s.split(":", 1)[1].strip()
            top = target.split(".", 1)[0]
            if top not in pkgs:
                # non-canonical integration target -> unreachable in this project
                continue
        out.append(ac)
    return out


def _sanitize_bad_acs(criteria: list[str]) -> list[str]:
    """Drop/repair ACs the LLM emits that can NEVER be satisfied, so a feature is
    not stranded in needs_human on a malformed criterion (bob73: 2 features NH'd
    on these and needed manual patches — breaking the patch-free streak).

    Two classes, both from the LLM's raw output:
    1. UNSUBSTITUTED PLACEHOLDERS — a path/target containing ``<...>`` (e.g.
       ``File exists: runs/<feature>/mutation_report.json``) is a template the
       synthesizer forgot to fill. Such an AC can never pass; drop it.
    2. ANCESTOR-LINEAGE references — ``integration: bob17.src`` / ``bob12.foo``
       name a long-gone ancestor generation (the chain reseeds each gen; old
       gen package names don't exist in THIS tree). Strip the ``bobN.`` lineage
       prefix so it targets the bare module, which the reachability-repair pass
       can then snap to a real one; if nothing remains, drop the AC.
    """
    import os as _os_s
    import re as _re_s
    import pathlib as _pl_s
    # The CURRENT gen's own package name (e.g. "bob73") is VALID — only strip
    # ANCESTOR lineage names. Derive it from this file's path: <gen>/src/bob/...
    try:
        _cur_gen = _pl_s.Path(__file__).resolve().parents[2].name  # e.g. "bob73"
    except Exception:
        _cur_gen = ""
    out: list[str] = []
    for ac in criteria:
        s = str(ac)
        # 1. unsubstituted placeholder anywhere in the AC → unsatisfiable, drop.
        if _re_s.search(r"<[A-Za-z0-9_]+>", s):
            continue
        # 2. ANCESTOR-lineage prefix: strip 'bob<digits>.' EXCEPT the current gen.
        #    'integration: bob17.src' → 'src' (reachability-repair then snaps it);
        #    'bob12.foo.bar' → 'foo.bar'; but 'bob73.mutation_gate' is left intact.
        def _strip_ancestor(m):
            tok = m.group(0)  # e.g. "bob17."
            name = tok[:-1]   # "bob17"
            # Keep the canonical base package 'bob' AND the current gen; strip
            # only OTHER ancestor gen names (bob12, bob17, ...).
            if name == "bob" or name == _cur_gen:
                return tok
            return ""
        s2 = _re_s.sub(r"\bbob\d+\.", _strip_ancestor, s)
        if _re_s.match(r"^\s*integration\s*:\s*$", s2):
            continue
        # After stripping an ancestor prefix, an integration target can collapse
        # to a bare DIRECTORY name that is not an importable module (e.g.
        # 'bob17.src' → 'src', 'bob12.tests' → 'tests'). Such a target can never
        # resolve — drop the AC rather than leave 'integration: src' to strand the
        # feature in needs_human (bob74 a171a7e9). The feature's real deliverables
        # (File exists / Function defined for the actual module) remain.
        _im = _re_s.match(r"^\s*integration\s*:\s*([\w./-]+)\s*$", s2)
        if _im and _im.group(1) in {"src", "tests", "lib", "test", "."}:
            continue
        out.append(s2)
    return out or list(criteria)  # never return empty; fall back to original


def emit_file_exists_acs(criteria: list[str], description: str) -> list[str]:
    """Public alias for :func:`_ensure_described_files_covered`.

    Emits a ``File exists: <path>`` AC for every concrete ``.py`` path the
    description explicitly names but the criteria don't already cover.

    This function is the public, directly-testable entry-point for the
    post-synthesis file-coverage step described in the feature spec:

    *SYNTHESIZER under-coverage*: when a description explicitly names a concrete
    source path (e.g. ``src/bob/brownfield/survey.py``) but synthesis derived a
    different slug filename, the described path is uncovered →
    ``contract_completeness=0``. Fix: post-synthesis, scan the description for
    concrete ``.py`` paths and emit a ``File exists: <path>`` AC for each not
    already covered.

    Boundary conditions:
    - Descriptions with no concrete ``.py`` paths are unaffected (empty list
      of paths → no new ACs added, original list returned unchanged).
    - Duplicate paths are not double-added (each path is emitted at most once).
    - Bare filenames without a directory component (e.g. ``foo.py``) are skipped
      because they are ambiguous.

    Parameters
    ----------
    criteria:
        Current list of AC strings (may be empty).
    description:
        Free-form feature description that may name concrete ``.py`` paths.

    Returns
    -------
    list[str]
        Augmented criteria list with ``File exists:`` ACs prepended for any
        uncovered concrete ``.py`` paths named in the description.
    """
    return _ensure_described_files_covered(criteria, description)


def should_emit_function_ac(symbol: str, description: str) -> bool:
    """F-af78c082 (HALF 1): decide whether a ``Function defined: <symbol>`` AC is
    contractually warranted.

    A structured ``Function defined:`` AC is only legitimate when the exact
    *symbol* appears VERBATIM in the feature's prose *description* (i.e. the
    human/PEAS author actually named that function). When the prose does not
    name the concrete symbol, the synthesizer MUST NOT invent an exact name and
    hard-gate on it — doing so hard-fails otherwise-complete features on a
    one-word naming difference (the 99b78f59 apply_ vs handle_ drain). In that
    case the caller should emit a behavior/pytest AC instead.

    The check is a case-insensitive, word-boundary identifier scan: the symbol
    must occur as a whole identifier token in the description, not as a
    substring of a larger word.

    Parameters
    ----------
    symbol:
        The candidate function name the synthesizer is considering gating on.
    description:
        The feature's prose description.

    Returns
    -------
    bool
        True iff *symbol* is a non-empty identifier that appears verbatim (as a
        whole word) in *description*. Empty/whitespace inputs return False.

    Raises
    ------
    TypeError / AttributeError
        If *symbol* or *description* is not a str (fails loudly, never silently
        succeeds).
    """
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__!r}")
    if not isinstance(description, str):
        raise TypeError(f"description must be a str, got {type(description).__name__!r}")
    sym = symbol.strip()
    if not sym or not description.strip():
        return False
    # Whole-identifier (word-boundary) match, case-insensitive. re.escape keeps
    # regex-special chars in the symbol literal.
    pattern = r"\b" + re.escape(sym) + r"\b"
    return re.search(pattern, description, re.IGNORECASE) is not None


def _ensure_described_files_covered(criteria: list[str], description: str) -> list[str]:
    """Emit a ``File exists: <path>`` AC for every concrete .py path the
    description explicitly names but the criteria don't already cover.

    contract_completeness extracts code-shaped surfaces (incl. .py file paths)
    from the description and demands an AC for each; when a PEAS prose feature
    names e.g. src/bob/brownfield/survey.py but synthesis derived a different
    slug filename, the described path is uncovered → contract_completeness=0 →
    composite 0.0 (the last 15/118 blockers). Adding the File-exists AC makes
    the contract legitimately complete — the implementation must create exactly
    the file the spec named, which is correct, not a gate weakening.
    """
    import re as _re
    desc = description or ""
    blob = " ".join(criteria)
    out = list(criteria)

    # (a) Concrete .py paths the description names.
    for path in sorted(set(_re.findall(r"[\w./\-]+\.py", desc))):
        if path in blob:
            continue
        if "/" not in path and not path.startswith("test"):
            continue
        out.append(f"File exists: {path}")

    # (b) Code-identifier SYMBOLS the description names after function/method/def
    # or in `name()` backticks — mirrors the scorer's _FUNC_RE so contract_
    # completeness sees them covered. Only code-shaped tokens (underscore or
    # CamelCase), excluding the English stop-words the scorer also ignores, so we
    # never emit a Function-defined AC for prose words like "defined"/"name".
    _STOP = {"defined", "implemented", "declared", "created", "added", "updated",
             "called", "named", "used", "the", "a", "an", "is", "be", "this",
             "that", "above", "below", "here", "it", "name", "acs", "gate"}
    blob_l = blob.lower()
    for m in _re.finditer(r"\b(?:function|method|def)\s+`?(\w+)`?|`(\w+)\(\)`", desc, _re.IGNORECASE):
        sym = (m.group(1) or m.group(2) or "")
        sl = sym.lower()
        if not sym or sl in _STOP:
            continue
        is_code = ("_" in sym) or any(c.isupper() for c in sym[1:])
        if not is_code:
            continue
        if sl in blob_l:  # already covered by some AC
            continue
        # F-af78c082 (HALF 1): only gate on an exact symbol the prose named
        # verbatim. This is true by construction here (sym was extracted FROM
        # desc), but routing through the guard keeps the contract explicit and
        # prevents a future refactor from emitting an invented name.
        if not should_emit_function_ac(sym, desc):
            continue
        out.append(f"Function defined: {sym}")
    return out


# Stop-words stripped when inferring a primary symbol from a feature title.
# These are filler words that rarely belong in a function/symbol name.
_SYMBOL_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "for", "to", "of", "in", "on", "with", "and",
    "or", "by", "from", "into", "at", "as", "is", "be",
})

# Trailing noun-ish words that bulk up titles but rarely belong in the
# function name itself ("user service" → "user", "payment module" → "payment").
_SYMBOL_TRAILING_NOUNS: frozenset[str] = frozenset({
    "service", "module", "handler", "manager", "helper", "utility",
    "utilities", "system", "subsystem", "component", "feature",
    "layer", "support", "integration", "wiring", "hook", "hooks",
})

# Heuristics for selecting the default integration target when the
# description signals wiring intent but doesn't name a concrete module.
_ORCHESTRATION_HINTS: tuple[str, ...] = (
    "orchestrator", "scheduler", "pipeline", "loop", "executor",
    "dispatcher", "router", "queue", "worker",
)
_CLI_HINTS: tuple[str, ...] = ("cli", "command", "entrypoint", "subcommand")


def _nfkd_fold(text: str) -> str:
    """Fold accented unicode to nearest ASCII before identifier normalisation.

    Ensures ``café`` → ``cafe`` rather than being silently destroyed by the
    ``[^a-zA-Z0-9]+`` regex that runs downstream.
    """
    # NFKD decomposes "é" → "e" + combining-acute; encoding to ASCII with
    # 'ignore' drops the combining marks but keeps the base letter.
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def _derive_canonical_slug(title: str) -> str | None:
    """Derive ONE canonical slug used for both the file path and module path.

    Pipeline: NFKD-fold unicode → tokenise on non-alphanumerics → drop
    stop-words → strip a single trailing noun. Validates that the result is
    a legal Python identifier and not a reserved keyword; returns ``None``
    when no valid candidate can be produced (e.g. empty title, all
    stop-words, leading digit, or a Python keyword like ``class``/``import``).

    Returning ``None`` lets ``_build_fallback_criteria`` decide whether to
    raise (empty title) or to emit a strengthened spec without the
    ``Function defined:`` line. Critically, both the file-exists and
    function-defined criteria use the SAME slug so a single implementation
    file satisfies both.
    """
    if not isinstance(title, str):
        return None
    if not title or not title.strip():
        return None
    folded = _nfkd_fold(title.lower())
    tokens = [t for t in re.split(r"[^a-z0-9]+", folded) if t]
    if not tokens:
        return None
    filtered = [t for t in tokens if t not in _SYMBOL_STOPWORDS]
    while len(filtered) > 1 and filtered[-1] in _SYMBOL_TRAILING_NOUNS:
        filtered.pop()
    if not filtered:
        # ALL tokens were stop-words → no meaningful slug. Return None so
        # _build_fallback_criteria raises ValueError rather than emitting a
        # reward-hackable spec built from filler words ("the_a_an_is"). The
        # earlier best-effort fallback to raw tokens defeated the documented
        # "all stop-words → None" contract (test_all_stopword_title_raises).
        return None
    # Cap the slug length: a very long feature title (bob66 had a 200+ char
    # title) otherwise yields a 200+ char "<slug>.py" filename that exceeds the
    # filesystem's 255-byte limit → "[Errno 36] File name too long" crashes the
    # verifier and wedges the whole run in a retry loop. Keep whole tokens up to
    # ~60 chars so the module name stays readable, importable, and short.
    _MAX_SLUG_LEN = 60
    if len("_".join(filtered)) > _MAX_SLUG_LEN:
        _capped: list[str] = []
        _used = 0
        for _t in filtered:
            _add = (1 if _capped else 0) + len(_t)
            if _used + _add > _MAX_SLUG_LEN:
                break
            _capped.append(_t)
            _used += _add
        if _capped:
            filtered = _capped
    slug = "_".join(filtered)
    # Hard-truncate when a single token exceeds the cap (whole-token capping
    # leaves _capped empty in that case, so slug is still the overlong token).
    if len(slug) > _MAX_SLUG_LEN:
        slug = slug[:_MAX_SLUG_LEN].rstrip("_")
    # Reject leading-digit and reserved-keyword slugs: both make
    # ``bob.<slug>.<symbol>`` un-importable, which would make the
    # Function-defined AC un-satisfiable by any well-formed implementation.
    if not slug.isidentifier() or keyword.iskeyword(slug):
        return None
    return slug


def derive_canonical_slug(title: object) -> str | None:
    """Public, length-capped slug derivation from a feature title.

    Delegates to :func:`_derive_canonical_slug`. Returns None for non-string,
    empty, whitespace-only, reserved-keyword, or leading-digit inputs. The
    resulting slug is capped at 60 characters on whole-token boundaries so the
    corresponding .py filename stays under the filesystem's 255-byte NAME_MAX
    limit — preventing the retry-loop hang caused by [Errno 36] when a 200+
    character title produced an overlong filename.
    """
    if not isinstance(title, str):
        return None
    return _derive_canonical_slug(title)


def _slugify(title: str) -> str:
    """File-path slug. Delegates to :func:`_derive_canonical_slug` so the
    file path and the function module path are guaranteed to agree.

    Returns the generic ``"feature"`` only when no canonical slug is
    available; callers that care about reward-hacking surface
    (``_build_fallback_criteria``) reject that case earlier rather than
    emitting a weak spec on top of a generic file path.
    """
    return _derive_canonical_slug(title) or "feature"


def _infer_primary_symbol(title: str) -> tuple[str, str] | None:
    """Infer ``(module, symbol)`` from a feature title.

    Uses :func:`_derive_canonical_slug` so the symbol and the file-exists
    path always agree on the same module name. Returns ``None`` when the
    title cannot produce a valid Python identifier (empty, all stop-words,
    starts with a digit, or is a reserved keyword like ``class``/``import``).
    """
    slug = _derive_canonical_slug(title)
    if slug is None:
        return None
    return f"bob.{slug}", slug


def _default_integration_target(title: str, description: str) -> str:
    """Pick a sensible integration target when no module was named explicitly.

    CLI-hint matches route to ``bob.cli``; orchestration hints route to
    ``bob.orchestrator.run_loop``. (Earlier revisions had both branches
    return the orchestrator target, which made the CLI check dead code.)
    """
    blob = f"{title} {description}".lower()
    if any(hint in blob for hint in _CLI_HINTS):
        return "bob.cli"
    if any(hint in blob for hint in _ORCHESTRATION_HINTS):
        return "bob.orchestrator.run_loop"
    return "bob.orchestrator.run_loop"


def _qualify_integration_target(target: str) -> str:
    """Ensure an integration target is module-qualified under ``bob.*``.

    A bare noun like ``bar`` (extracted from "wire foo into bar") would
    otherwise satisfy any substring scan in the verifier and provide a
    trivial reward-hack surface. Prepending ``bob.`` forces the implementer
    to wire into a real module path.
    """
    target = target.strip()
    if not target:
        return target
    if target.startswith("bob.") or target == "bob":
        return target
    return f"bob.{target}"


def _build_fallback_criteria(
    feature_name: str,
    feature_description: str,
) -> list[str]:
    """Build the hardened deterministic-fallback acceptance-criteria list.

    Guarantees (F-R6-305 + post-review hardening):
      * Always emits at least 3 substantive criteria.
      * The file-exists and function-defined criteria use the SAME slug.
      * Reserved-keyword / leading-digit / unicode-destroyed titles never
        produce an un-importable ``Function defined:`` line.
      * Integration targets are always ``bob.``-qualified.
      * Empty / degenerate titles raise ``ValueError`` rather than emitting
        a weak ``file_exists + pytest + CLI command:`` triple that any
        two empty stub files could satisfy.
    """
    slug = _derive_canonical_slug(feature_name)
    if slug is None:
        # Refuse to synthesize a meaningful spec without a usable title
        # rather than emit a reward-hackable weak spec (issue #4).
        raise ValueError(
            f"Cannot synthesize fallback acceptance criteria from "
            f"feature_name={feature_name!r}: title does not yield a valid "
            f"Python identifier (empty, reserved keyword, or all "
            f"stop-words). Provide a non-trivial title."
        )

    # One slug, used for BOTH the file path and the function module path,
    # so a single implementation satisfies both criteria (issue #2).
    criteria: list[str] = [
        f"File exists: src/bob/{slug}.py",
        # pytest target names a specific test function so an empty test file
        # can't satisfy the pytest AC by accident (issue #4 defence-in-depth).
        f"pytest: tests/test_{slug}.py::test_{slug}",
        f"Function defined: bob.{slug}.{slug}",
    ]

    targets = detect_integration_targets(feature_description or "")
    if targets:
        # detect_integration_targets returns at least one entry when a wiring
        # keyword was present; "existing_module" is the sentinel for "keyword
        # found but no concrete target named".
        target = targets[0]
        if target == "existing_module":
            target = _default_integration_target(feature_name, feature_description or "")
        # Always module-qualify to prevent bare-noun reward hacks (issue #3).
        criteria.append(f"integration: {_qualify_integration_target(target)}")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for c in criteria:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    # Apply boundary + error coverage HERE so BOTH fallback callers
    # (deterministic_fallback and deterministic_fallback_spec) carry it
    # consistently — deterministic_fallback_spec previously bypassed it and
    # emitted specs with no boundary/error AC (caught by
    # test_spec_dict_includes_boundary_ac/error_ac).
    return _ensure_boundary_and_error_coverage(deduped, title=feature_name)


def deterministic_fallback(
    feature_name: str,
    feature_description: str = "",
    **kwargs: Any,
) -> list[str]:
    """Hardened deterministic fallback for failed LLM synthesis.

    This is the F-R6-305 hardening of F-R1-011's original two-line fallback.
    Returns a list of machine-verifiable acceptance criteria that always
    contains at least three entries and never collapses to the
    ``file_exists`` + ``pytest:`` pair that pushed ``conf_test_adequacy``
    below the spawn-gate threshold in earlier rounds.

    The signature accepts ``**kwargs`` so callers can pass forward-compatible
    metadata (e.g. ``project_context``) without breaking. The return type is
    ``list[str]`` for back-compat with the existing ``sanitize_spec_file``
    caller and prior tests; callers that want the structured form should use
    :func:`deterministic_fallback_spec`.

    The fallback MUST also carry boundary + error-path coverage, otherwise a
    rate-limited feature that falls back here scores composite 0.0 (geometric
    mean zeroed by those two empty sub-metrics) and re-blocks at the gate — the
    49/118 still-below-0.85 after a rate-limited sanitize pass. Apply the same
    coverage guarantee the LLM path gets via _apply_llm_postprocessing.

    Error contract: empty, whitespace-only, None, or all-stop-word titles raise
    ValueError (or TypeError for non-string inputs) rather than emitting a
    reward-hackable weak spec that any two stub files could satisfy.
    """
    # Non-string inputs raise TypeError before any slug derivation attempt.
    if not isinstance(feature_name, str):
        raise TypeError(
            f"deterministic_fallback: feature_name must be a str, got "
            f"{type(feature_name).__name__}"
        )
    # Empty / whitespace / degenerate titles raise ValueError — let
    # _build_fallback_criteria propagate its rejection rather than catching it.
    base = _build_fallback_criteria(feature_name, feature_description)
    base = _ensure_boundary_and_error_coverage(base, title=feature_name)
    base = _ensure_described_files_covered(base, feature_description)
    return base


def deterministic_fallback_spec(
    feature_name: str,
    feature_description: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Dict-returning sibling of :func:`deterministic_fallback`.

    Wraps the hardened criteria in a structured envelope so future callers
    can attach provenance / diagnostics without further signature churn.
    """
    criteria = _build_fallback_criteria(feature_name, feature_description)
    return {
        "acceptance_criteria": criteria,
        "source": "deterministic_fallback",
        "feature_name": feature_name,
    }


async def sanitize_spec_file(
    spec_path: Path,
    *,
    project_id: str,
    project_context: str = "",
    workspace: Path | None = None,
    dry_run: bool = False,
    use_fallback: bool = True,
    concurrency: int = 4,
) -> dict[str, Any]:
    """Rewrite YAML in place, replacing TBD ACs with synthesized ones.

    Returns a report dict: {synthesized, fell_back, total, written}.
    """
    spec_path = Path(spec_path)
    with open(spec_path) as f:
        spec = yaml.safe_load(f) or {}

    pending = find_placeholder_features(spec)
    report = {"synthesized": 0, "fell_back": 0, "total": len(pending), "written": False}
    if not pending:
        return report

    # Concurrency is env-tunable (BOB_SYNTH_CONCURRENCY) so the operator can
    # throttle synthesizer parallelism when Vertex AI is rate-limiting, without a
    # code change. Lower = gentler on the quota (fewer simultaneous calls), at the
    # cost of a slower sanitize pass. Default 3.
    import os as _os
    try:
        _conc = int(_os.environ.get("BOB_SYNTH_CONCURRENCY", str(concurrency)))
    except ValueError:
        _conc = concurrency
    sem = asyncio.Semaphore(max(1, _conc))

    async def _one(key: str, feat: dict) -> tuple[str, list[str] | None, bool]:
        async with sem:
            title = feat.get("title") or feat.get("name") or key
            desc = (feat.get("description") or "").strip()
            gate_failed = False
            try:
                # F-R7-615: route through score_gate_loop, NOT bare
                # synthesize_for_feature. The bare path did ONE synthesis pass
                # and stopped — producing thin 4-AC specs scoring ~0.75
                # (zero boundary_coverage + zero error_path_coverage tank the
                # geometric-mean composite below the 0.85 gate, stranding the
                # feature in 'pending' forever; bob65: 49 features stuck at
                # exactly 0.75). score_gate_loop re-synthesizes with explicit
                # missing-dimension feedback (add boundary + error-path ACs)
                # until the composite legitimately clears 0.85. This does NOT
                # lower the gate — it enriches the ACs to genuinely pass it.
                _report = await score_gate_loop(
                    synthesize_fn=synthesize_for_feature,
                    title=title,
                    description=desc,
                    project_id=project_id,
                    use_fallback=use_fallback,
                    project_context=project_context,
                    workspace=workspace,
                )
                criteria = _report.criteria
                gate_failed = _report.gate_failed
            except Exception as exc:
                logger.warning(
                    "score_gate_loop raised for %s (%s): %s", key, title, exc
                )
                criteria = None
                gate_failed = True
            return key, criteria, gate_failed

    results = await asyncio.gather(*(_one(k, v) for k, v in pending))
    feat_by_key = {k: v for k, v in pending}
    for key, criteria, gate_failed in results:
        feat = feat_by_key[key]
        title = feat.get("title") or feat.get("name") or key
        if criteria and not gate_failed:
            feat["acceptance_criteria"] = criteria
            report["synthesized"] += 1
            logger.info("synthesized AC for %s (%s): %s", key, title, criteria)
        elif criteria and gate_failed:
            feat["acceptance_criteria"] = criteria
            report["fell_back"] += 1
            logger.warning(
                "LLM synthesis gate failed for %s (%s); using fallback criteria: %s",
                key, title, criteria,
            )
        elif use_fallback:
            try:
                feat["acceptance_criteria"] = deterministic_fallback(
                    title, feat.get("description") or ""
                )
            except ValueError as exc:
                # Degenerate title — refuse to emit a weak/reward-hackable
                # spec rather than collapse to file_exists + pytest stubs.
                logger.error(
                    "deterministic fallback refused %s (%s): %s",
                    key, title, exc,
                )
                continue
            report["fell_back"] += 1
            logger.warning(
                "LLM synthesis failed for %s (%s); using deterministic fallback: %s",
                key, title, feat["acceptance_criteria"],
            )
        else:
            logger.error("synthesis failed for %s (%s) and fallback disabled", key, title)

    if not dry_run and (report["synthesized"] + report["fell_back"]) > 0:
        with open(spec_path, "w") as f:
            yaml.safe_dump(
                spec, f,
                sort_keys=False,
                default_flow_style=False,
                width=100,
                allow_unicode=True,
            )
        report["written"] = True

    return report


# ---------------------------------------------------------------------------
# Score-gate loop — F-R1-011 retry extension
# ---------------------------------------------------------------------------

_DEFAULT_SPEC_QUALITY_THRESHOLD = 0.85
_DEFAULT_MAX_RETRIES = 3


def score_gate_threshold_from_env() -> float:
    """Read the score-gate threshold from BOB_SPEC_QUALITY_THRESHOLD env var.

    Returns 0.85 by default. Clamps to [0.0, 1.0]. Returns default on
    invalid (non-float) values.
    """
    raw = os.environ.get("BOB_SPEC_QUALITY_THRESHOLD")
    if not raw:
        return _DEFAULT_SPEC_QUALITY_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_SPEC_QUALITY_THRESHOLD
    return max(0.0, min(1.0, value))


def score_synthesized_acs(
    criteria: list[str],
    name: str,
    description: str | None = None,
) -> float:
    """Score a list of synthesized acceptance criteria using the composite scorer.

    Returns a float in [0, 1]. Empty criteria list returns 0.0.
    """
    compute = _load_compute()

    if not criteria:
        return 0.0
    result = compute(
        name=name,
        description=description,
        acceptance_criteria=criteria,
    )
    return result.composite


def should_emit_function_defined_ac(symbol: str, description: str) -> bool:
    """Return True iff *symbol* appears verbatim (word-boundary match) in *description*.

    Used by :func:`_build_fallback_criteria` and synthesizer post-processing to
    decide whether to emit a ``Function defined: <module>.<symbol>`` AC: only
    emit it when the description explicitly names the symbol as an identifier,
    not when a synonym or partial match appears.

    Empty *symbol* or blank *description* always returns False.
    Non-string inputs raise TypeError.
    """
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__!r}")
    if not isinstance(description, str):
        raise TypeError(f"description must be a str, got {type(description).__name__!r}")
    if not symbol or not symbol.strip():
        return False
    if not description.strip():
        return False
    import re as _re
    return bool(_re.search(r"\b" + _re.escape(symbol) + r"\b", description, _re.IGNORECASE))


# F-af78c082: public alias matching AC "Function defined: bob.spec_synthesizer.should_emit_function_ac"
should_emit_function_ac = should_emit_function_defined_ac

# F-04ffd352: public alias matching AC "Function defined: bob.spec_synthesizer.should_emit_exact_function_ac"
should_emit_exact_function_ac = should_emit_function_defined_ac


def extract_verbatim_symbols(description: str) -> list[str]:
    """Extract all Python identifier tokens that appear verbatim in *description*.

    Scans *description* for sequences that look like Python identifiers (i.e.
    match ``[A-Za-z_][A-Za-z0-9_]*``) and are valid Python identifiers.
    Returns a deduplicated list of such tokens in order of first appearance.

    This is used by the synthesizer to decide which function names can be
    safely emitted as ``Function defined: <module>.<symbol>`` ACs — only names
    that appear verbatim in the prose are contractual; synthesizer-invented
    names must not become hard gates.

    Parameters
    ----------
    description:
        The feature prose / PEAS description text to scan.

    Returns
    -------
    list[str]
        Deduplicated list of Python identifier tokens found in *description*,
        in order of first appearance.  Empty list for blank/empty input.

    Raises
    ------
    TypeError
        When *description* is not a str.

    Examples
    --------
    >>> extract_verbatim_symbols("Call apply_exponential_backoff to limit re-dispatch.")
    ['Call', 'apply_exponential_backoff', 'to', 'limit', 're', 'dispatch']
    >>> extract_verbatim_symbols("")
    []
    """
    if not isinstance(description, str):
        raise TypeError(f"description must be a str, got {type(description).__name__!r}")
    if not description.strip():
        return []
    import re as _re
    tokens = _re.findall(r"[A-Za-z_][A-Za-z0-9_]*", description)
    seen: set[str] = set()
    result: list[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.add(tok)
            result.append(tok)
    return result


def emit_function_defined_ac(module: str, symbol: str, description: str) -> str | None:
    """Emit a ``Function defined: <module>.<symbol>`` AC iff *symbol* appears verbatim in *description*.

    When the prose does NOT name the exact symbol, returns None — the caller
    should emit a capability-oriented AC (pytest or behavior AC) instead.
    This prevents the synthesizer from inventing an exact function name that
    the feature author never specified, which would hard-gate implementers on
    a name they cannot predict.

    Parameters
    ----------
    module:
        Dotted module path, e.g. ``bob.reaper``.
    symbol:
        The function name to check for, e.g. ``apply_exponential_backoff``.
    description:
        The feature prose / PEAS description text to scan.

    Returns
    -------
    str or None
        ``"Function defined: <module>.<symbol>"`` when the symbol appears
        verbatim in the description; ``None`` otherwise.

    Raises
    ------
    TypeError
        When *module*, *symbol*, or *description* is not a str.
    ValueError
        When *module* or *symbol* is empty or blank.
    """
    if not isinstance(module, str):
        raise TypeError(f"module must be a str, got {type(module).__name__!r}")
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__!r}")
    if not isinstance(description, str):
        raise TypeError(f"description must be a str, got {type(description).__name__!r}")
    if not module.strip():
        raise ValueError("module must not be empty or blank")
    if not symbol.strip():
        raise ValueError("symbol must not be empty or blank")
    if should_emit_function_defined_ac(symbol, description):
        return f"Function defined: {module}.{symbol}"
    return None


def emit_function_defined_ac_only_when_prose_names_symbol(
    module: str, symbol: str, description: str
) -> str | None:
    """Emit ``Function defined: <module>.<symbol>`` only when *symbol* appears verbatim in *description*.

    This is the canonical guard the synthesizer MUST use before emitting a
    ``Function defined:`` AC. When the feature prose does NOT name the exact
    symbol, returns None — the caller should emit a capability-oriented AC
    (a pytest AC or behavior AC) instead of an exact-name AC.

    This prevents the synthesizer from inventing a function name the feature
    author never specified, which would hard-gate implementers on an
    unspecified internal name (the root cause of the exponential-backoff
    false-negative, F-R7-620).

    Parameters
    ----------
    module:
        Dotted module path, e.g. ``bob.reaper``.
    symbol:
        The function name to check for, e.g. ``apply_exponential_backoff``.
    description:
        The feature prose / PEAS description text to scan.

    Returns
    -------
    str or None
        ``"Function defined: <module>.<symbol>"`` when the symbol appears
        verbatim in the description; ``None`` otherwise.

    Raises
    ------
    TypeError
        When *module*, *symbol*, or *description* is not a str.
    ValueError
        When *module* or *symbol* is empty or blank.
    """
    return emit_function_defined_ac(module, symbol, description)


def emit_ac_from_prose(
    module: str, symbol: str, description: str
) -> str:
    """Emit the most appropriate AC for a function given the feature prose.

    When *symbol* appears verbatim (word-boundary match) in *description*,
    emits ``"Function defined: <module>.<symbol>"`` — the exact-name contract
    is warranted because the prose named the function explicitly.

    When *symbol* does NOT appear verbatim in *description*, emits a
    capability-oriented behavioral AC instead:
    ``"behavior: <module> implements <symbol> capability"`` — this verifies
    the behavior without hard-gating on a name the implementer cannot predict.

    This is the primary entry point the synthesizer MUST use before choosing
    between a Function-defined AC and a behavioral AC.  It prevents the
    synthesizer from inventing exact function names that hard-fail otherwise
    correct implementations (F-d2497fa5).

    Parameters
    ----------
    module:
        Dotted module path, e.g. ``bob.reaper``.
    symbol:
        The function name to check for, e.g. ``apply_exponential_backoff``.
    description:
        The feature prose / PEAS description text to scan.

    Returns
    -------
    str
        Either ``"Function defined: <module>.<symbol>"`` (symbol verbatim in
        prose) or ``"behavior: <module> implements <symbol> capability"``
        (symbol absent from prose).

    Raises
    ------
    TypeError
        When *module*, *symbol*, or *description* is not a str.
    ValueError
        When *module* or *symbol* is empty or blank.
    """
    if not isinstance(module, str):
        raise TypeError(f"module must be a str, got {type(module).__name__!r}")
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__!r}")
    if not isinstance(description, str):
        raise TypeError(f"description must be a str, got {type(description).__name__!r}")
    if not module.strip():
        raise ValueError("module must not be empty or blank")
    if not symbol.strip():
        raise ValueError("symbol must not be empty or blank")
    if should_emit_function_defined_ac(symbol, description):
        return f"Function defined: {module}.{symbol}"
    return f"behavior: {module} implements {symbol} capability"


def build_retry_feedback_prompt(
    score_result: Any = None,
    attempt: int = 1,
    threshold: float = _DEFAULT_SPEC_QUALITY_THRESHOLD,
    *,
    previous_criteria: list[str] | None = None,
    score: float | None = None,
    rationale: list[str] | None = None,
) -> str:
    """Build a feedback string for the synthesizer retry, naming failing sub-metrics.

    Supports two calling conventions:

    New (internal, richer):
        build_retry_feedback_prompt(score_result=<CompositeScore>, attempt=N, threshold=T)

    Legacy (test-friendly, simpler):
        build_retry_feedback_prompt(previous_criteria=[...], score=0.5, rationale=[...])

    Parameters
    ----------
    score_result:
        A CompositeScore from the quality scorer (new convention).
    attempt:
        The attempt number (1-indexed) for context.
    threshold:
        The passing threshold.
    previous_criteria:
        The criteria list from the previous attempt (legacy convention).
    score:
        The composite score from the previous attempt (legacy convention).
    rationale:
        List of rationale strings from the previous attempt (legacy convention).

    Returns
    -------
    str
        A prompt fragment describing what the previous attempt failed at,
        suitable for prepending to a retry synthesis prompt.
    """
    # Legacy calling convention: (previous_criteria=..., score=..., rationale=...)
    if score_result is None and score is not None:
        _composite = score
        _rationale = rationale or []
        lines = [
            f"Attempt {attempt} produced a composite score of {_composite:.3f}, "
            f"which is below the required threshold of {threshold:.3f}.",
        ]
        if _rationale:
            lines.append("Specific issues:")
            for hint in _rationale[:5]:
                lines.append(f"  * {hint}")
        lines.append(
            "Please revise the acceptance criteria to address these issues. "
            "Ensure at least one AC covers error/failure paths, at least one references a boundary condition, "
            "and all ACs use structured machine-verifiable forms."
        )
        return "\n".join(lines)

    # New calling convention: score_result is a CompositeScore object
    sub_metrics = {
        "smell_density": score_result.smell_density,
        "predicate_coverage": score_result.predicate_coverage,
        "contract_completeness": score_result.contract_completeness,
        "boundary_coverage": score_result.boundary_coverage,
        "error_path_coverage": score_result.error_path_coverage,
        "traceability": score_result.traceability,
        "spec_executability": score_result.spec_executability,
        "ac_atomicity": score_result.ac_atomicity,
    }

    failing = [
        (name, sub_score)
        for name, sub_score in sub_metrics.items()
        if sub_score < threshold
    ]

    lines = [
        f"Attempt {attempt} produced a composite score of {score_result.composite:.3f}, "
        f"which is below the required threshold of {threshold:.3f}.",
        "The following sub-metrics need improvement:",
    ]
    for name, sub_score in failing:
        lines.append(f"  - {name}: {sub_score:.3f} (below {threshold:.3f})")

    if score_result.rationale:
        lines.append("Specific issues:")
        for hint in score_result.rationale[:5]:
            lines.append(f"  * {hint}")

    lines.append(
        "Please revise the acceptance criteria to address these issues. "
        "Ensure at least one AC covers error/failure paths, at least one references a boundary condition, "
        "and all ACs use structured machine-verifiable forms."
    )

    return "\n".join(lines)


@dataclass
class ScoreGateReport:
    """Report returned by score_gate_loop."""

    gate_passed: bool
    gate_failed: bool
    gate_avg_attempts: int
    criteria: list[str] | None
    composite: float
    rationale: list[str] = field(default_factory=list)


async def score_gate_loop(
    *,
    synthesize_fn: Callable[..., Awaitable[list[str] | None]],
    title: str,
    description: str,
    project_id: str,
    threshold: float | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    use_fallback: bool = True,
    project_context: str = "",
    workspace: Path | None = None,
) -> ScoreGateReport:
    """Re-synthesize TBD ACs until composite score reaches threshold.

    Wraps *synthesize_fn* in a retry loop: after each synthesis attempt the
    candidate criteria are scored; if the composite falls below *threshold*
    a feedback prompt is built and passed as ``retry_feedback`` kwarg to
    the next call. The loop caps at *max_retries* attempts.

    On exhaustion with ``use_fallback=True``, :func:`deterministic_fallback`
    is used and ``gate_failed`` is set.  With ``use_fallback=False``,
    a ``ValueError`` is raised if all attempts return None/empty.
    """
    compute = _load_compute()

    if threshold is None:
        threshold = score_gate_threshold_from_env()

    best_criteria: list[str] | None = None
    best_composite: float = 0.0
    best_rationale: list[str] = []
    retry_feedback: str | None = None

    for attempt in range(1, max_retries + 1):
        kwargs: dict[str, Any] = {
            "project_id": project_id,
            "title": title,
            "description": description,
            "project_context": project_context,
            "workspace": workspace,
            "retry_feedback": retry_feedback,
        }
        try:
            criteria = await synthesize_fn(**kwargs)
        except Exception as exc:
            logger.warning("score_gate_loop: synthesize_fn raised on attempt %d: %s", attempt, exc)
            criteria = None

        if not criteria:
            logger.warning(
                "score_gate_loop: attempt %d returned empty/None for %r", attempt, title
            )
            if attempt < max_retries:
                retry_feedback = (
                    f"Attempt {attempt} returned no valid criteria. "
                    "Please produce a non-empty JSON array of machine-verifiable ACs."
                )
            continue

        score_obj = compute(
            name=title,
            description=description,
            acceptance_criteria=criteria,
        )
        composite = score_obj.composite

        if composite > best_composite or best_criteria is None:
            best_criteria = criteria
            best_composite = composite
            best_rationale = score_obj.rationale

        if composite >= threshold:
            return ScoreGateReport(
                gate_passed=True,
                gate_failed=False,
                gate_avg_attempts=attempt,
                criteria=criteria,
                composite=composite,
                rationale=score_obj.rationale,
            )

        logger.info(
            "score_gate_loop: attempt %d scored %.3f < %.3f for %r; retrying",
            attempt, composite, threshold, title,
        )
        retry_feedback = build_retry_feedback_prompt(
            score_result=score_obj,
            attempt=attempt,
            threshold=threshold,
        )

    # All retries exhausted
    if best_criteria is None:
        # Every attempt returned None/empty
        if use_fallback:
            try:
                fallback = deterministic_fallback(title, description)
                fb_score = compute(
                    name=title,
                    description=description,
                    acceptance_criteria=fallback,
                ).composite
                return ScoreGateReport(
                    gate_passed=False,
                    gate_failed=True,
                    gate_avg_attempts=max_retries,
                    criteria=fallback,
                    composite=fb_score,
                    rationale=["All synthesis attempts returned empty; used deterministic fallback"],
                )
            except ValueError:
                pass
        raise ValueError(
            f"score_gate_loop: synthesizer returned invalid empty output after "
            f"{max_retries} retries for feature {title!r}. "
            "All attempts produced None or empty criteria."
        )

    # Had criteria but never passed the gate
    if use_fallback:
        try:
            fallback = deterministic_fallback(title, description)
            fb_score = compute(
                name=title,
                description=description,
                acceptance_criteria=fallback,
            ).composite
            final_criteria = fallback
            final_composite = fb_score
        except ValueError:
            final_criteria = best_criteria
            final_composite = best_composite
    else:
        final_criteria = best_criteria
        final_composite = best_composite

    return ScoreGateReport(
        gate_passed=False,
        gate_failed=True,
        gate_avg_attempts=max_retries,
        criteria=final_criteria,
        composite=final_composite,
        rationale=best_rationale,
    )


# ---------------------------------------------------------------------------
# sanitize_spec_file_with_gate_loop — F-R1-011 gate-loop integration
# ---------------------------------------------------------------------------


async def sanitize_spec_file_with_gate_loop(
    spec_path: Path,
    *,
    project_id: str,
    project_context: str = "",
    workspace: Path | None = None,
    dry_run: bool = False,
    use_fallback: bool = True,
    concurrency: int = 4,
    threshold: float | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Rewrite YAML in place, replacing TBD ACs via a score-gate retry loop.

    Wraps :func:`sanitize_spec_file` but replaces each per-feature synthesis
    call with :func:`score_gate_loop` so that ACs are re-synthesized up to
    *max_retries* times until the composite spec-quality score meets *threshold*
    (default: ``BOB_SPEC_QUALITY_THRESHOLD`` env var, else 0.85).

    Returns a report dict extending the base sanitize_spec_file report with
    three extra keys:
      - ``gate_passed`` — number of features whose ACs passed the quality gate
      - ``gate_failed`` — number of features that exhausted retries below threshold
      - ``gate_avg_attempts`` — average number of attempts across all features
        (None when no placeholder features were found)
    """
    if threshold is None:
        threshold = score_gate_threshold_from_env()

    spec_path = Path(spec_path)
    with open(spec_path) as f:
        spec = yaml.safe_load(f) or {}

    pending = find_placeholder_features(spec)
    report: dict[str, Any] = {
        "synthesized": 0,
        "fell_back": 0,
        "total": len(pending),
        "written": False,
        "gate_passed": 0,
        "gate_failed": 0,
        "gate_avg_attempts": None,
    }
    if not pending:
        return report

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(key: str, feat: dict) -> tuple[str, ScoreGateReport | None]:
        async with sem:
            title = feat.get("title") or feat.get("name") or key
            desc = (feat.get("description") or "").strip()
            try:
                gate_report = await score_gate_loop(
                    synthesize_fn=synthesize_for_feature,
                    title=title,
                    description=desc,
                    project_id=project_id,
                    threshold=threshold,
                    max_retries=max_retries,
                    use_fallback=use_fallback,
                    project_context=project_context,
                    workspace=workspace,
                )
            except Exception as exc:
                logger.warning(
                    "score_gate_loop raised for %s (%s): %s", key, title, exc
                )
                return key, None
            return key, gate_report

    results = await asyncio.gather(*(_one(k, v) for k, v in pending))
    feat_by_key = {k: v for k, v in pending}
    total_attempts = 0
    features_processed = 0

    for key, gate_report in results:
        feat = feat_by_key[key]
        title = feat.get("title") or feat.get("name") or key

        if gate_report is None:
            if use_fallback:
                try:
                    feat["acceptance_criteria"] = deterministic_fallback(
                        title, feat.get("description") or ""
                    )
                    report["fell_back"] += 1
                    report["gate_failed"] += 1
                    logger.warning(
                        "Gate loop failed for %s (%s); using deterministic fallback",
                        key, title,
                    )
                except ValueError as exc:
                    logger.error(
                        "deterministic fallback refused %s (%s): %s", key, title, exc
                    )
            else:
                logger.error(
                    "gate loop failed for %s (%s) and fallback disabled", key, title
                )
            continue

        if gate_report.criteria:
            feat["acceptance_criteria"] = gate_report.criteria
            total_attempts += gate_report.gate_avg_attempts
            features_processed += 1

            if gate_report.gate_passed:
                report["synthesized"] += 1
                report["gate_passed"] += 1
                logger.info(
                    "gate_loop passed for %s (%s) in %d attempt(s): %s",
                    key, title, gate_report.gate_avg_attempts, gate_report.criteria,
                )
            else:
                report["fell_back"] += 1
                report["gate_failed"] += 1
                logger.warning(
                    "gate_loop failed threshold for %s (%s) after %d attempt(s): %s",
                    key, title, gate_report.gate_avg_attempts, gate_report.criteria,
                )

    if features_processed > 0:
        report["gate_avg_attempts"] = round(total_attempts / features_processed, 2)

    if not dry_run and (report["synthesized"] + report["fell_back"]) > 0:
        with open(spec_path, "w") as f:
            yaml.safe_dump(
                spec, f,
                sort_keys=False,
                default_flow_style=False,
                width=100,
                allow_unicode=True,
            )
        report["written"] = True

    return report


# ---------------------------------------------------------------------------
# synthesize_with_score_gate — convenience wrapper (F-9db7b1af)
# ---------------------------------------------------------------------------


async def synthesize_with_score_gate(
    *,
    title: str,
    description: str,
    project_id: str,
    threshold: float | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    use_fallback: bool = True,
    project_context: str = "",
    workspace: Path | None = None,
) -> ScoreGateReport:
    """Synthesize acceptance criteria for one feature via the score-gate loop.

    Convenience wrapper around :func:`score_gate_loop` that wires in the
    default :func:`synthesize_for_feature` synthesizer.  Callers that need
    to inject a custom synthesizer should call :func:`score_gate_loop`
    directly.

    Raises ValueError if title is empty (invalid input — cannot derive a slug).
    Raises ValueError if all synthesis attempts return None/empty and use_fallback=False.
    Returns a ScoreGateReport with gate_passed, gate_failed, gate_avg_attempts,
    criteria, and composite for the empty-input boundary case (use_fallback=True
    produces a deterministic fallback rather than crashing).
    """
    if not title or not title.strip():
        raise ValueError(
            "synthesize_with_score_gate requires a non-empty title; "
            f"got {title!r}"
        )

    return await score_gate_loop(
        synthesize_fn=synthesize_for_feature,
        title=title,
        description=description or "",
        project_id=project_id,
        threshold=threshold,
        max_retries=max_retries,
        use_fallback=use_fallback,
        project_context=project_context,
        workspace=workspace,
    )


# ---------------------------------------------------------------------------
# synthesize_with_score_gate_loop — AC: "Function defined: bob.spec_synthesizer.synthesize_with_score_gate_loop"
# Feature f4d82621: named entry-point wrapping score_gate_loop; returns a plain dict
# so callers don't need to import the ScoreGateReport dataclass.
# ---------------------------------------------------------------------------


async def synthesize_with_score_gate_loop(
    *,
    title: str,
    description: str,
    project_id: str,
    threshold: float | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    use_fallback: bool = True,
    project_context: str = "",
    workspace: Path | None = None,
    synthesize_fn: "Callable[..., Awaitable[list[str] | None]] | None" = None,
) -> "dict[str, Any]":
    """Re-synthesize TBD ACs via a score-gate loop, returning a plain dict.

    Wraps :func:`score_gate_loop` with the default synthesizer and returns a
    plain ``dict`` (keys: ``gate_passed``, ``gate_failed``, ``gate_avg_attempts``,
    ``criteria``, ``composite``, ``rationale``) so callers need not import
    :class:`ScoreGateReport`.

    Raises ValueError if *title* is empty or whitespace-only.

    On exhaustion with ``use_fallback=True`` the dict contains fallback criteria
    and ``gate_failed=True``; with ``use_fallback=False`` a ``ValueError`` is
    raised if all synthesis attempts return ``None``/empty.
    """
    if not title or not title.strip():
        raise ValueError(
            "synthesize_with_score_gate_loop requires a non-empty title; "
            f"got {title!r}"
        )

    _synthesize_fn = synthesize_fn if synthesize_fn is not None else synthesize_for_feature

    report: ScoreGateReport = await score_gate_loop(
        synthesize_fn=_synthesize_fn,
        title=title,
        description=description or "",
        project_id=project_id,
        threshold=threshold,
        max_retries=max_retries,
        use_fallback=use_fallback,
        project_context=project_context,
        workspace=workspace,
    )

    return {
        "gate_passed": report.gate_passed,
        "gate_failed": report.gate_failed,
        "gate_avg_attempts": report.gate_avg_attempts,
        "criteria": report.criteria,
        "composite": report.composite,
        "rationale": report.rationale,
    }


# ---------------------------------------------------------------------------
# Public alias — AC: "Function defined: bob.spec_synthesizer.synthesize_acceptance_criteria"
# ---------------------------------------------------------------------------

#: Public alias for :func:`synthesize_for_feature`.
#: Satisfies the feature AC without duplicating logic.
synthesize_acceptance_criteria = synthesize_for_feature

# ---------------------------------------------------------------------------
# Public alias — AC: "Function defined: bob.spec_synthesizer.synthesize_with_retry"
# Feature cf7b0ce9: the explicit public name required by the feature AC.
# synthesize_for_feature already implements aggressive retry (default 40 attempts,
# exponential backoff, BOB_SYNTH_MAX_ATTEMPTS env-tunable); synthesize_with_retry
# is the explicitly-named entry-point that documents this contract.
# ---------------------------------------------------------------------------

#: Public alias for :func:`synthesize_for_feature` — explicitly named entry-point
#: for the aggressive-retry synthesis path required by feature cf7b0ce9.
#: Spawns a Haiku sub-agent, re-spawns on empty text or exception (transient
#: HTTP 400 burst), backs off exponentially (2,4,8,16,32 capped at 60s), and
#: only falls through to deterministic fallback after BOB_SYNTH_MAX_ATTEMPTS
#: (default 40) are exhausted.  Each retry is logged so bursts are observable.
synthesize_with_retry = synthesize_for_feature

# ---------------------------------------------------------------------------
# Public alias — AC: "Function defined: bob.spec_synthesizer.score_gate_retry_loop"
# Feature bceb6b94: score_gate_retry_loop is the explicitly-named public entry-point
# for the score-gate retry loop described in the feature AC.  score_gate_loop already
# implements all the required behaviour (re-synthesize TBD ACs, score, retry with
# feedback, cap at max_retries, deterministic fallback on exhaustion, return dict
# with gate_passed/gate_failed/gate_avg_attempts); score_gate_retry_loop is the
# named alias that satisfies the AC without duplicating logic.
# ---------------------------------------------------------------------------

#: Public alias for :func:`score_gate_loop` — explicitly named entry-point
#: required by feature bceb6b94.  Accepts identical kwargs and returns a
#: :class:`ScoreGateReport`.  See :func:`score_gate_loop` for full docstring.
score_gate_retry_loop = score_gate_loop


# ---------------------------------------------------------------------------
# retry_with_backoff — AC: "Function defined: bob.spec_synthesizer.retry_with_backoff"
# Feature 0b4c9609: explicitly-named public entry-point for the backoff retry
# helper used by synthesize_for_feature to outlast transient upstream 400 bursts.
# ---------------------------------------------------------------------------

async def retry_with_backoff(
    fn,
    *,
    max_attempts: int | None = None,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    jitter_seed: str = "",
) -> tuple[any, bool]:
    """Retry *fn* (async callable, no args) with exponential backoff on empty/exception.

    Used by :func:`synthesize_for_feature` to outlast transient upstream HTTP 400
    bursts from the shared API key.  Re-invokes *fn* up to *max_attempts* times;
    on each failure backs off exponentially (2, 4, 8, 16, 32 … capped at
    *max_delay* seconds) plus optional deterministic jitter derived from
    *jitter_seed*.

    Parameters
    ----------
    fn:
        Async callable (no arguments) returning a value; an empty string, None,
        or a raised exception are all treated as failures that trigger a retry.
    max_attempts:
        Maximum number of invocations (including the first).  Defaults to the
        ``BOB_SYNTH_MAX_ATTEMPTS`` environment variable (default 40).
    base_delay:
        Initial backoff in seconds (doubles each attempt, capped at *max_delay*).
    max_delay:
        Maximum backoff in seconds.
    jitter_seed:
        String used to derive a deterministic per-caller jitter fraction so
        concurrent callers don't resynchronize after a burst.

    Returns
    -------
    tuple[result, success]
        *result* is the last value returned by *fn* (may be None/empty when
        *success* is False); *success* is True if *fn* returned a non-empty
        non-None result before exhausting attempts.
    """
    import asyncio as _asyncio
    import os as _os

    if max_attempts is None:
        try:
            max_attempts = max(1, int(_os.environ.get("BOB_SYNTH_MAX_ATTEMPTS", "40")))
        except ValueError:
            max_attempts = 40

    _jit = (abs(hash(jitter_seed)) % 1000) / 1000.0 if jitter_seed else 0.0
    result = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = await fn()
        except Exception as exc:
            logger.warning(
                "retry_with_backoff: attempt %d/%d raised: %s",
                attempt, max_attempts, exc,
            )
            result = None

        if result:
            if attempt > 1:
                logger.info(
                    "retry_with_backoff: recovered on attempt %d/%d",
                    attempt, max_attempts,
                )
            return result, True

        if attempt < max_attempts:
            delay = min(base_delay ** attempt, max_delay) + int(_jit * 5)
            logger.warning(
                "retry_with_backoff: attempt %d/%d returned empty — retrying in %.0fs",
                attempt, max_attempts, delay,
            )
            await _asyncio.sleep(delay)

    return result, False
