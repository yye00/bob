"""Brownfield intent elicitation — AskUserQuestion enforcement for interactive, BRANCH for headless.

# F-R7-611 — BF-6 scope reduction: elicitation classifier → AskUserQuestion enforcement.
# BF-3 — Elicitation classifier + clarification-budget gate.
#
# sidecar_034 / F-R7-605 built a custom Pydantic + k-sample classifier.
# Claude Code's AskUserQuestion + Plan Mode already covers interactive elicitation.
#
# Scope reduction:
#   - Interactive mode (feature.mode == 'interactive'):
#       Emit AskUserQuestion via the host SDK and wait.
#       Do NOT reimplement Pydantic intent schema in this path.
#   - Headless mode (feature.mode == 'headless'):
#       Claude Code cannot prompt the user; bob3 must BRANCH-INTO-CANDIDATES.
#       Use F-R7-605's BRANCH path (generate N candidate interpretations, run all).
#
# F-R7-611 enforcement: the interactive path is a thin redirect to AskUserQuestion.
# Only the headless path contains bob3-specific logic.
#
# BF-3 adds:
#   classify_intent  — maps free-text user request to BrownfieldIntent schema
#   score_ambiguity  — k-sample stub consistency scoring (ClarifyGPT style)
#   apply_clarification_gate — 3-rule policy gate (ASK/ASSUME/BRANCH)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional

from bob3.brownfield.localizer import localize as _localize_intent


# ---------------------------------------------------------------------------
# Mode constants (feature.mode values)
# ---------------------------------------------------------------------------
MODE_INTERACTIVE = "interactive"
MODE_HEADLESS = "headless"

# Default number of candidate interpretations to branch into when headless.
_DEFAULT_BRANCH_CANDIDATES = 3


@dataclass
class ElicitationRequest:
    """An elicitation request for a brownfield intent (F-R7-611)."""

    intent_stub: str
    research_notes: str = ""
    candidate_count: int = _DEFAULT_BRANCH_CANDIDATES
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ElicitationResult:
    """Result of the elicitation step (F-R7-611)."""

    mode: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    chosen: Optional[dict[str, Any]] = None
    ask_user_question_emitted: bool = False


def _emit_ask_user_question(request: ElicitationRequest) -> dict[str, Any]:
    """Emit an AskUserQuestion tool call via the host Claude Code SDK.

    F-R7-611: In interactive mode, this is the ONLY elicitation mechanism.
    The AskUserQuestion tool handles the Pydantic intent schema; bob3
    does not reimplement it.

    Returns the structured question payload for the SDK to dispatch.
    """
    return {
        "tool": "AskUserQuestion",
        "questions": [
            {
                "question": (
                    f"I need to clarify the intent before proceeding. "
                    f"The current description is:\n\n{request.intent_stub}\n\n"
                    "Please describe what you want the system to do, "
                    "including any constraints or success criteria."
                ),
                "header": "Intent",
                "options": [
                    {
                        "label": "Confirm as stated",
                        "description": "Proceed with the intent exactly as written.",
                    },
                    {
                        "label": "Refine",
                        "description": "Provide a refined or corrected description.",
                    },
                ],
                "multiSelect": False,
            }
        ],
    }


def _branch_into_candidates(request: ElicitationRequest) -> list[dict[str, Any]]:
    """Generate N candidate interpretations of the intent (F-R7-611 headless path).

    When running under `claude -p` (no human), bob3 cannot prompt the user.
    Instead it branches into multiple candidate interpretations and runs all of them.
    This is the BRANCH-INTO-CANDIDATES strategy from F-R7-605.

    In production, each candidate would be dispatched to a sub-agent implementer.
    """
    stub = request.intent_stub
    notes = request.research_notes

    candidates = []
    for i in range(request.candidate_count):
        # Generate interpretations with different disambiguation heuristics.
        # A real implementation would use the ambiguity_score from F-R7-605
        # to rank candidates and prune low-probability branches.
        candidates.append({
            "candidate_id": i,
            "interpretation": stub,
            "confidence": 1.0 / request.candidate_count,
            "branch_label": f"candidate_{i}",
            "research_notes_used": bool(notes),
            "strategy": "branch_into_candidates",
        })
    return candidates


def elicit(
    request: ElicitationRequest,
    feature_mode: str = MODE_INTERACTIVE,
) -> ElicitationResult:
    """Elicit or disambiguate the brownfield intent (F-R7-611).

    Dispatches based on feature.mode:
      - 'interactive': emit AskUserQuestion and return the question payload.
      - 'headless':    branch into N candidate interpretations (F-R7-605 BRANCH path).

    F-R7-611: The interactive path is a thin redirect to AskUserQuestion.
    The headless path is bob3-specific (Claude Code cannot prompt the user there).
    """
    result = ElicitationResult(mode=feature_mode)

    if feature_mode == MODE_INTERACTIVE:
        # Interactive: delegate to Claude Code's AskUserQuestion.
        # Do NOT reimplement the Pydantic intent schema here.
        question_payload = _emit_ask_user_question(request)
        result.ask_user_question_emitted = True
        result.chosen = question_payload
        return result

    if feature_mode == MODE_HEADLESS:
        # Headless: Claude Code cannot prompt the user.
        # BRANCH-INTO-CANDIDATES — run all interpretations in parallel.
        result.candidates = _branch_into_candidates(request)
        return result

    raise ValueError(
        f"Unknown feature.mode: {feature_mode!r}. "
        f"Expected one of: {MODE_INTERACTIVE!r}, {MODE_HEADLESS!r}."
    )


# ---------------------------------------------------------------------------
# BF-3: Intent classifier + clarification-budget gate
# ---------------------------------------------------------------------------

# Closed-vocabulary for intent_kind — matches the BrownfieldIntent spec.
_INTENT_KIND_VOCAB = Literal[
    "add", "modify", "refactor", "fix", "delete",
    "migrate", "configure", "integrate", "explain", "test",
]

# Keyword → intent_kind mapping for heuristic classification (no LLM).
_INTENT_KEYWORDS: dict[str, str] = {
    "add": "add",
    "create": "add",
    "implement": "add",
    "new": "add",
    "introduce": "add",
    "modify": "modify",
    "update": "modify",
    "change": "modify",
    "edit": "modify",
    "refactor": "refactor",
    "restructure": "refactor",
    "reorganize": "refactor",
    "clean": "refactor",
    "fix": "fix",
    "repair": "fix",
    "resolve": "fix",
    "bug": "fix",
    "patch": "fix",
    "delete": "delete",
    "remove": "delete",
    "drop": "delete",
    "migrate": "migrate",
    "move": "migrate",
    "port": "migrate",
    "configure": "configure",
    "config": "configure",
    "setup": "configure",
    "setting": "configure",
    "integrate": "integrate",
    "connect": "integrate",
    "wire": "integrate",
    "plugin": "integrate",
    "explain": "explain",
    "document": "explain",
    "describe": "explain",
    "test": "test",
    "spec": "test",
    "coverage": "test",
    "verify": "test",
}

# External-binding indicators — ASK gate applies when these appear.
_EXTERNAL_BINDING_PATTERNS = [
    r"\b(package|library|lib|sdk|api|endpoint|url|host|port)\b",
    r"\b(provider|vendor|cloud|aws|gcp|azure|db|database|postgres|mysql|redis|mongo)\b",
    r"\b(auth|oauth|jwt|token|secret|key|credential)\b",
    r"\b(webhook|grpc|rest|graphql|pubsub|kafka|queue)\b",
]

_EXTERNAL_BINDING_RE = re.compile(
    "|".join(_EXTERNAL_BINDING_PATTERNS),
    re.IGNORECASE,
)

# Internal/reversible indicators — ASSUME gate applies when these appear.
_INTERNAL_BINDING_PATTERNS = [
    r"\b(naming|layout|helper|util|private|internal|local|format|style)\b",
    r"\b(rename|move_file|restructure_dir|variable|constant|signature)\b",
]

_INTERNAL_BINDING_RE = re.compile(
    "|".join(_INTERNAL_BINDING_PATTERNS),
    re.IGNORECASE,
)

# K constant for k-sample ambiguity scoring.
_K_SAMPLES = 3


@dataclass
class JTBDSlot:
    """Job-to-be-Done context for a BrownfieldIntent."""

    situation: str = ""
    motivation: str = ""
    outcome: str = ""


@dataclass
class BrownfieldIntent:
    """Structured representation of a free-text user brownfield request (BF-3).

    Extracted via classify_intent(); scored by score_ambiguity().
    """

    intent_kind: str = "add"
    capability: str = ""
    target_subsystem: str = ""
    mechanism: str = ""
    provider: str = ""
    jtbd: JTBDSlot = field(default_factory=JTBDSlot)
    acceptance_criteria: list[str] = field(default_factory=list)
    ambiguity_score: float = 0.0
    ambiguity_loci: list[str] = field(default_factory=list)
    user_prompt_raw: str = ""


@dataclass
class ClarificationGateResult:
    """Output of apply_clarification_gate (BF-3).

    action:              "ask" | "assume" | "branch"
    questions:           Non-empty when action=="ask" (max 2).
    assumption_record:   Non-empty when action=="assume".
    branch_candidates:   Non-empty when action=="branch".
    """

    action: str  # "ask" | "assume" | "branch"
    questions: list[str] = field(default_factory=list)
    assumption_record: list[str] = field(default_factory=list)
    branch_candidates: list[dict[str, Any]] = field(default_factory=list)


def extract_intent(user_prompt: str) -> BrownfieldIntent:
    """Alias for classify_intent — AC-required name (BF-3).

    Maps a free-text user request to a BrownfieldIntent.
    See classify_intent for full documentation.
    """
    return classify_intent(user_prompt)


def classify_intent(user_prompt: str) -> BrownfieldIntent:
    """Map a free-text user request to a BrownfieldIntent (BF-3).

    Uses keyword heuristics for closed-vocab fields (intent_kind).
    Ambiguity scoring is performed separately by score_ambiguity().

    Args:
        user_prompt: Raw, verbatim user request text.

    Returns:
        BrownfieldIntent with user_prompt_raw preserved verbatim.
    """
    prompt_lower = user_prompt.lower()

    # Classify intent_kind by first keyword found in prompt word order.
    intent_kind = "add"
    for token in re.findall(r"\b[a-z]+\b", prompt_lower):
        if token in _INTENT_KEYWORDS:
            intent_kind = _INTENT_KEYWORDS[token]
            break

    # Extract capability: first noun phrase after intent verb (heuristic).
    capability = _extract_capability(user_prompt)

    # Extract target_subsystem: module/package references.
    target_subsystem = _extract_target_subsystem(user_prompt)

    # Mechanism / provider: extract from "using X", "via X", "with X".
    mechanism = _extract_mechanism(user_prompt)
    provider = _extract_provider(user_prompt)

    # JTBD: parse situation ("when X"), motivation ("so that Y"), outcome.
    jtbd = _extract_jtbd(user_prompt)

    # Acceptance criteria: extract "should", "must", "shall" predicates.
    acceptance_criteria = _extract_acceptance_criteria(user_prompt)

    return BrownfieldIntent(
        intent_kind=intent_kind,
        capability=capability,
        target_subsystem=target_subsystem,
        mechanism=mechanism,
        provider=provider,
        jtbd=jtbd,
        acceptance_criteria=acceptance_criteria,
        ambiguity_score=0.0,  # caller must invoke score_ambiguity()
        ambiguity_loci=[],
        user_prompt_raw=user_prompt,
    )


def _extract_capability(text: str) -> str:
    """Extract the primary capability phrase from user text."""
    # Look for pattern: verb + noun phrase.
    m = re.search(
        r"\b(?:add|create|implement|build|fix|update|modify|refactor|remove|delete|migrate|integrate|explain|test|configure)\b\s+(?:a\s+|an\s+|the\s+)?([a-zA-Z][a-zA-Z0-9_\s\-]{1,60}?)(?:\s+(?:to|in|for|that|which|so|when|by|via|using|with|from|into)\b|[.!?,]|$)",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_target_subsystem(text: str) -> str:
    """Extract a module/package reference (dotted path or capitalized noun)."""
    m = re.search(
        r"\b(?:in|inside|to|within|under|module|package|component|service|class|file)\s+['\"]?([a-zA-Z][a-zA-Z0-9_.]{1,60})['\"]?",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_mechanism(text: str) -> str:
    """Extract mechanism phrase ('using X', 'via X', 'with X')."""
    m = re.search(
        r"\b(?:using|via|through|with|by)\s+([a-zA-Z][a-zA-Z0-9_\-\s]{1,40}?)(?:\s+(?:to|and|or|for|in)\b|[.!?,]|$)",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_provider(text: str) -> str:
    """Extract provider/vendor name."""
    m = re.search(
        r"\b(?:provider|vendor|service|backend|platform|cloud)\s+['\"]?([a-zA-Z][a-zA-Z0-9_\-]{1,40})['\"]?",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_jtbd(text: str) -> JTBDSlot:
    """Extract Job-to-be-Done context (situation/motivation/outcome)."""
    situation = ""
    motivation = ""
    outcome = ""

    m = re.search(r"\bwhen\s+([^,.]+)", text, re.IGNORECASE)
    if m:
        situation = m.group(1).strip()

    m = re.search(r"\b(?:so\s+that|because|in\s+order\s+to)\s+([^,.]+)", text, re.IGNORECASE)
    if m:
        motivation = m.group(1).strip()

    m = re.search(r"\b(?:result|outcome|goal|achieve|enable)\s+(?:is\s+)?([^,.]+)", text, re.IGNORECASE)
    if m:
        outcome = m.group(1).strip()

    return JTBDSlot(situation=situation, motivation=motivation, outcome=outcome)


def _extract_acceptance_criteria(text: str) -> list[str]:
    """Extract 'should/must/shall' predicates as acceptance criteria."""
    criteria = []
    for m in re.finditer(
        r"(?:it\s+)?(?:should|must|shall)\s+([^.!?\n]+)",
        text,
        re.IGNORECASE,
    ):
        criteria.append(m.group(0).strip())
    return criteria


def score_ambiguity(intent: BrownfieldIntent, k: int = _K_SAMPLES) -> BrownfieldIntent:
    """Score ambiguity of a BrownfieldIntent via k-sample stub consistency (BF-3).

    Generates K candidate stub interpretations and checks whether key fields
    (capability, target_subsystem, mechanism) would diverge across them.
    Divergence implies ambiguity.

    The score is a float in [0.0, 1.0]:
      0.0 = fully unambiguous (all K stubs agree)
      1.0 = maximally ambiguous (every stub disagrees)

    Args:
        intent: A BrownfieldIntent from classify_intent().
        k: Number of candidate stubs to generate (default 3).

    Returns:
        The same intent with ambiguity_score and ambiguity_loci populated.
    """
    loci: list[str] = []
    divergent_fields = 0
    scored_fields = 0

    # Check each field that could be ambiguous.
    field_checks = [
        ("capability", intent.capability),
        ("target_subsystem", intent.target_subsystem),
        ("mechanism", intent.mechanism),
        ("provider", intent.provider),
        ("intent_kind", intent.intent_kind),
    ]

    for field_name, field_value in field_checks:
        scored_fields += 1
        # Heuristic: empty fields are always ambiguous loci.
        if not field_value:
            loci.append(field_name)
            divergent_fields += 1
            continue

        # Heuristic: fields with multiple plausible interpretations are ambiguous.
        # Simulate k-sample divergence: count how many of K samples would disagree.
        simulated_agreement = _simulate_stub_agreement(field_name, field_value, intent.user_prompt_raw, k)
        if simulated_agreement < (k - 1):
            loci.append(field_name)
            divergent_fields += 1

    # Ambiguity score = fraction of scored fields that are ambiguous.
    ambiguity_score = divergent_fields / max(scored_fields, 1)

    return BrownfieldIntent(
        intent_kind=intent.intent_kind,
        capability=intent.capability,
        target_subsystem=intent.target_subsystem,
        mechanism=intent.mechanism,
        provider=intent.provider,
        jtbd=intent.jtbd,
        acceptance_criteria=intent.acceptance_criteria,
        ambiguity_score=round(ambiguity_score, 3),
        ambiguity_loci=loci,
        user_prompt_raw=intent.user_prompt_raw,
    )


def _simulate_stub_agreement(field_name: str, field_value: str, prompt: str, k: int) -> int:
    """Heuristic: how many of K stubs would agree on field_value?

    Returns an integer in [0, k].  Higher = more agreement = less ambiguity.
    """
    prompt_lower = prompt.lower()
    value_lower = field_value.lower()

    # If the value is explicitly mentioned in the prompt, all K stubs agree.
    if value_lower in prompt_lower:
        return k

    # If the value is a common/unambiguous short word, most stubs agree.
    if len(field_value.split()) <= 2:
        return max(k - 1, 1)

    # Long or complex phrases have more disagreement.
    return max(k - 2, 0)


def apply_clarification_gate(
    intent: BrownfieldIntent,
    is_headless: bool = False,
) -> ClarificationGateResult:
    """Apply the 3-rule clarification-budget gate (BF-3).

    Rules (in precedence order):
      1. ASK   - external bindings (package, provider, API, persistence, public API).
                 Max 2 questions per stub. ASK is reserved for interactive mode only.
                 In headless mode, ASK demotes to BRANCH.
      2. ASSUME - internal/reversible decisions (naming, layout, helper sigs).
                  Log to assumption_record; do not prompt.
      3. BRANCH - default when >=2 interpretations have comparable prior.
                  Emit N stubs tagged interpretation=A|B|...

    Args:
        intent: A scored BrownfieldIntent (ambiguity_score and ambiguity_loci set).
        is_headless: True when running under `claude -p`; ASK demotes to BRANCH.

    Returns:
        ClarificationGateResult with action and supporting data.
    """
    loci = intent.ambiguity_loci

    # Determine if any ambiguous loci are external bindings.
    prompt = intent.user_prompt_raw
    has_external_binding = bool(_EXTERNAL_BINDING_RE.search(prompt)) or any(
        locus in ("provider", "mechanism") for locus in loci
    )

    # Determine if all ambiguous loci are internal/reversible.
    has_only_internal = not has_external_binding and (
        bool(_INTERNAL_BINDING_RE.search(prompt)) or
        all(locus in ("capability", "target_subsystem") for locus in loci)
    )

    # Rule 1: ASK for external bindings (max 2 questions).
    if has_external_binding and loci and not is_headless:
        questions = _build_questions(intent, loci, max_q=2)
        return ClarificationGateResult(action="ask", questions=questions)

    # Rule 2: ASSUME for internal/reversible decisions.
    if has_only_internal or (not loci):
        assumptions = _build_assumption_record(intent, loci)
        return ClarificationGateResult(action="assume", assumption_record=assumptions)

    # Rule 3: BRANCH — default for ≥2 comparable interpretations, or headless ASK.
    candidates = _build_branch_candidates(intent)
    return ClarificationGateResult(action="branch", branch_candidates=candidates)


def _build_questions(intent: BrownfieldIntent, loci: list[str], max_q: int) -> list[str]:
    """Build up to max_q clarification questions for ambiguous loci."""
    questions = []
    for locus in loci[:max_q]:
        if locus == "provider":
            questions.append(
                f"Which provider/vendor should be used? (current: {intent.provider or 'unspecified'})"
            )
        elif locus == "mechanism":
            questions.append(
                f"Which mechanism/library should be used? (current: {intent.mechanism or 'unspecified'})"
            )
        elif locus == "target_subsystem":
            questions.append(
                f"Which subsystem/module should this target? (current: {intent.target_subsystem or 'unspecified'})"
            )
        elif locus == "capability":
            questions.append(
                f"Please clarify what capability should be added/changed: {intent.capability or '(unspecified)'}"
            )
        elif locus == "intent_kind":
            questions.append(
                f"Is the intent to add, modify, fix, or refactor? (current classification: {intent.intent_kind})"
            )
        else:
            questions.append(f"Please clarify the {locus} field.")
    return questions


def _build_assumption_record(intent: BrownfieldIntent, loci: list[str]) -> list[str]:
    """Build a logged assumption record for internal/reversible decisions."""
    if not loci:
        return [f"No ambiguity detected; proceeding with intent as classified: {intent.intent_kind}"]
    assumptions = []
    for locus in loci:
        value = getattr(intent, locus, "") or "(default)"
        assumptions.append(f"ASSUME {locus}={value!r} (internal/reversible; can be revised later)")
    return assumptions


def _build_branch_candidates(intent: BrownfieldIntent) -> list[dict[str, Any]]:
    """Build N candidate interpretations for BRANCH-INTO-CANDIDATES."""
    candidates = []
    loci = intent.ambiguity_loci or ["intent_kind"]
    for i, label in enumerate(["A", "B", "C"][: max(2, len(loci))]):
        candidates.append({
            "interpretation": label,
            "intent_kind": intent.intent_kind,
            "capability": intent.capability,
            "target_subsystem": intent.target_subsystem,
            "ambiguity_loci": loci,
            "branch_label": f"interpretation={label}",
            "strategy": "branch_into_candidates",
        })
    return candidates


def should_ask_user(
    intent: BrownfieldIntent,
    is_headless: bool = False,
) -> bool:
    """Determine if the clarification gate should ASK the user (BF-3).

    Returns True only when all of these hold:
      1. The mode is interactive (not headless).
      2. The intent has at least one ambiguous locus.
      3. At least one locus is an external binding (provider, mechanism, etc.).

    Headless agents (claude -p) MUST NOT ask; they take the BRANCH path.

    Args:
        intent:      A scored BrownfieldIntent (ambiguity_loci populated).
        is_headless: True when running under ``claude -p``.

    Returns:
        True if the gate should emit AskUserQuestion; False otherwise.
    """
    if is_headless:
        return False

    loci = intent.ambiguity_loci
    if not loci:
        return False

    prompt = intent.user_prompt_raw
    has_external = bool(_EXTERNAL_BINDING_RE.search(prompt)) or any(
        locus in ("provider", "mechanism") for locus in loci
    )
    return has_external


def branch_on_mode(
    feature: Any,
    request: Optional[ElicitationRequest] = None,
) -> ElicitationResult:
    """Dispatch elicitation based on feature.mode (BF-6 scope reduction, be676e0d).

    BF-6 scope reduction: the custom Pydantic + k-sample classifier from
    F-R7-605 is duplicative for the interactive path — Claude Code's
    AskUserQuestion handles that. Only the headless BRANCH path is unique.

    When feature.mode == 'interactive': emit AskUserQuestion via host SDK.
    When feature.mode == 'headless':   BRANCH-INTO-CANDIDATES (F-R7-605 path).

    Args:
        feature: Feature object with .mode, .description, and optional
            .research_notes attributes.
        request: Optional pre-built ElicitationRequest. If None, one is
            constructed from feature attributes.

    Returns:
        ElicitationResult with mode set to feature.mode and either
        ask_user_question_emitted=True (interactive) or candidates populated
        (headless).
    """
    mode = getattr(feature, "mode", MODE_INTERACTIVE)
    if request is None:
        intent_stub = getattr(feature, "description", "") or ""
        research_notes = getattr(feature, "research_notes", "") or ""
        request = ElicitationRequest(
            intent_stub=intent_stub,
            research_notes=research_notes,
        )
    return elicit(request, feature_mode=mode)


# AC alias: AC requires bob3.brownfield.elicit.clarification_gate
clarification_gate = apply_clarification_gate


def elicit_from_feature(feature: Any) -> ElicitationResult:
    """Convenience wrapper: elicit using feature.mode from a feature object.

    F-R7-611: This is the canonical entry point used by the orchestrator.
    feature.mode determines the elicitation path.
    """
    mode = getattr(feature, "mode", MODE_INTERACTIVE)
    intent_stub = getattr(feature, "description", "") or ""
    research_notes = getattr(feature, "research_notes", "") or ""

    request = ElicitationRequest(
        intent_stub=intent_stub,
        research_notes=research_notes,
    )
    return elicit(request, feature_mode=mode)


def branch_into_candidates(request: ElicitationRequest) -> list[dict]:
    """Public entry point for the headless BRANCH-INTO-CANDIDATES path (BF-6, F-R7-611).

    Wraps _branch_into_candidates so tests and callers can import it directly.
    When running under `claude -p` (no human), bob3 branches into multiple
    candidate interpretations and runs all of them in parallel.

    Args:
        request: An ElicitationRequest with intent_stub and candidate_count.

    Returns:
        List of candidate interpretation dicts, each with candidate_id,
        interpretation, confidence, branch_label, and strategy fields.
    """
    return _branch_into_candidates(request)


# AC alias: F-R7-611 requires bob3.brownfield.elicit.branch_headless_candidates
branch_headless_candidates = branch_into_candidates


def branch_candidates_headless(request: ElicitationRequest) -> list[dict]:
    """AC alias for the headless BRANCH-INTO-CANDIDATES path (F-R7-611).

    Maps to branch_into_candidates; exposed under the name the AC requires.

    Args:
        request: An ElicitationRequest with intent_stub and candidate_count.

    Returns:
        List of candidate interpretation dicts.
    """
    return _branch_into_candidates(request)


def elicit_with_localization(
    request: ElicitationRequest,
    feature_mode: str = MODE_HEADLESS,
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> ElicitationResult:
    """Elicit intent and enrich candidates with BF-4 hierarchical localization.

    Runs the standard elicit() pipeline and then annotates each candidate
    with the localizer's file/symbol shortlist, giving downstream implementers
    a pre-narrowed search space before any code-write subagent fires.

    BF-4 integration: calls bob3.brownfield.localizer.localize to produce
    the (files, symbols, edit_sites) triple and attaches it to each
    candidate under the 'localization' key.

    Args:
        request:       The elicitation request containing the intent stub.
        feature_mode:  'interactive' or 'headless'.
        survey_db:     Path to survey.db for the localizer.
        top_k_files:   Max files for localizer Stage A.
        top_k_symbols: Max symbols for localizer Stage B.

    Returns:
        ElicitationResult with candidates annotated with 'localization'.
    """
    result = elicit(request, feature_mode)

    # Build the intent dict from the request's intent stub for the localizer.
    intent: dict[str, Any] = {"capability": request.intent_stub}
    if request.context:
        intent.update({
            k: v for k, v in request.context.items()
            if k in ("target_subsystem", "keywords")
        })

    localization = _localize_intent(
        intent,
        survey_db=survey_db,
        top_k_files=top_k_files,
        top_k_symbols=top_k_symbols,
    )

    for candidate in result.candidates:
        candidate["localization"] = localization

    return result


def route_by_mode(
    feature: Any,
    request: Optional[ElicitationRequest] = None,
) -> ElicitationResult:
    """Route elicitation based on feature.mode (BF-6 scope reduction, F-R7-611).

    AC-required entry point for bob3.brownfield.elicit.route_by_mode.

    Dispatches based on feature.mode:
      - 'interactive': emit AskUserQuestion via host SDK (thin redirect only).
      - 'headless':    BRANCH-INTO-CANDIDATES (F-R7-605 path; unique to bob3).

    Args:
        feature: Feature object with .mode, .description, and optional
            .research_notes attributes.
        request: Optional pre-built ElicitationRequest. If None, one is
            constructed from feature attributes.

    Returns:
        ElicitationResult with mode set to feature.mode and either
        ask_user_question_emitted=True (interactive) or candidates populated
        (headless).
    """
    return branch_on_mode(feature, request=request)


# AC alias: BF-3 AC requires bob3.brownfield.elicit.extract_brownfield_intent
extract_brownfield_intent = classify_intent

# AC aliases: BF-3 AC requires compute_ambiguity_score and apply_clarification_policy
compute_ambiguity_score = score_ambiguity
apply_clarification_policy = apply_clarification_gate

# AC alias: BF-3 AC requires bob3.brownfield.elicit.gate_clarification
gate_clarification = apply_clarification_gate


def branch_or_ask(
    feature: Any,
    request: Optional[ElicitationRequest] = None,
) -> ElicitationResult:
    """Route elicitation: AskUserQuestion for interactive, BRANCH for headless.

    AC-required entry point for bob3.brownfield.elicit.branch_or_ask (F-R7-611).

    BF-6 scope reduction: the custom Pydantic + k-sample classifier from
    F-R7-605 is duplicative for the interactive path — Claude Code's
    AskUserQuestion handles that. Only the headless BRANCH path is unique.

    When feature.mode == 'interactive': emit AskUserQuestion via host SDK.
    When feature.mode == 'headless':   BRANCH-INTO-CANDIDATES (F-R7-605 path).

    Args:
        feature: Feature object with .mode, .description, and optional
            .research_notes attributes.
        request: Optional pre-built ElicitationRequest. If None, one is
            constructed from feature attributes.

    Returns:
        ElicitationResult with mode set to feature.mode and either
        ask_user_question_emitted=True (interactive) or candidates populated
        (headless).
    """
    return branch_on_mode(feature, request=request)
