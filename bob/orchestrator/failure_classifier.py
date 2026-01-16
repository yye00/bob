"""
Failure Classification for BOB
================================

Analyzes error patterns to classify why a task is failing repeatedly.
Uses both heuristic pattern matching and LLM-based analysis.

Ported from autonomous-coding/failure_classifier.py and adapted for BOB's Task model.

Failure Categories:
- TOO_BIG: Task is too complex, needs decomposition
- MISSING_INFO: Missing information (docs, examples), needs research
- WRONG_INFRA: Missing packages/tools/environment, needs user
- BAD_ASSUMPTIONS: Fundamental approach is wrong, needs restructure
- NEEDS_RESEARCH: Specific technical issue, needs targeted research
"""

import re
from dataclasses import dataclass
from typing import Optional

from bob.models.base import FailureType, Task


@dataclass
class ClassificationResult:
    """Result of failure classification."""

    failure_type: FailureType
    confidence: float  # 0.0 to 1.0
    reason: str
    research_queries: list[str]
    recommended_action: str
    details: dict


# Patterns for heuristic classification
INFRASTRUCTURE_PATTERNS = [
    # Missing packages
    (r"ModuleNotFoundError:\s*No module named ['\"](\w+)['\"]", "missing_module"),
    (r"ImportError:\s*cannot import name", "import_error"),
    (r"ImportError:\s*No module named", "missing_module"),
    (r"Package .+ is not installed", "missing_package"),
    (r"command not found", "missing_command"),
    (r"npm ERR! code ENOENT", "npm_missing"),
    (r"Could not find a version that satisfies", "pip_version_conflict"),
    (r"No matching distribution found", "pip_not_found"),
    # Environment issues
    (r"PermissionError", "permission_denied"),
    (r"EACCES: permission denied", "permission_denied"),
    (r"Connection refused", "connection_refused"),
    (r"ECONNREFUSED", "connection_refused"),
    (r"SSL: CERTIFICATE_VERIFY_FAILED", "ssl_error"),
    # Database/service issues
    (r"OperationalError.*connection", "db_connection"),
    (r"redis\.exceptions\.ConnectionError", "redis_connection"),
    (r"Cannot connect to", "service_unavailable"),
]

COMPLEXITY_PATTERNS = [
    # Tests timing out or hanging
    (r"timeout.*exceeded", "timeout"),
    (r"TimeoutError", "timeout"),
    (r"Exceeded.*time limit", "timeout"),
    # Too many changes needed
    (r"file\(s\) changed.*\d{2,} insertions", "large_changes"),
    (r"RecursionError", "recursion"),
    (r"maximum recursion depth exceeded", "recursion"),
    # Circular dependencies
    (r"circular import", "circular_import"),
    (r"circular dependency", "circular_dep"),
]

MISSING_INFO_PATTERNS = [
    # API/documentation issues
    (r"AttributeError: .+ has no attribute ['\"](\w+)['\"]", "unknown_attribute"),
    (r"TypeError:.*unexpected keyword argument", "api_mismatch"),
    (r"TypeError:.*takes \d+ positional arguments", "api_mismatch"),
    (r"deprecated", "deprecated_api"),
    # Unknown references
    (r"NameError: name ['\"](\w+)['\"] is not defined", "undefined_name"),
    (r"ReferenceError", "undefined_reference"),
]

BAD_ASSUMPTIONS_PATTERNS = [
    # Logic/assertion errors
    (r"AssertionError", "assertion_failed"),
    (r"Expected .+ but got", "expectation_mismatch"),
    (r"does not match", "mismatch"),
    # Type errors indicating wrong approach
    (r"TypeError: cannot .+ types", "type_mismatch"),
    (r"incompatible types", "type_mismatch"),
    # Wrong structure
    (r"KeyError:", "missing_key"),
    (r"IndexError:", "index_error"),
    (r"ValueError:", "value_error"),
]

REPEATED_SAME_ERROR_THRESHOLD = 2  # If same error appears N times, likely stuck


def classify_by_patterns(errors: list[str]) -> Optional[ClassificationResult]:
    """
    Classify failure using pattern matching on error messages.

    Args:
        errors: List of error messages to analyze

    Returns:
        ClassificationResult or None if no clear pattern found
    """
    combined_errors = "\n".join(errors).lower()

    # Check for infrastructure issues (highest priority - needs user)
    for pattern, error_type in INFRASTRUCTURE_PATTERNS:
        if re.search(pattern, combined_errors, re.IGNORECASE):
            match = re.search(pattern, combined_errors, re.IGNORECASE)
            matched_text = match.group(0) if match else error_type

            return ClassificationResult(
                failure_type=FailureType.WRONG_INFRA,
                confidence=0.85,
                reason=f"Detected infrastructure issue: {error_type}",
                research_queries=[],  # No research for infra - needs user
                recommended_action="Request user to install missing dependencies or fix environment",
                details={
                    "pattern_type": error_type,
                    "matched_text": matched_text,
                },
            )

    # Check for complexity issues
    for pattern, error_type in COMPLEXITY_PATTERNS:
        if re.search(pattern, combined_errors, re.IGNORECASE):
            return ClassificationResult(
                failure_type=FailureType.TOO_BIG,
                confidence=0.75,
                reason=f"Task appears too complex: {error_type}",
                research_queries=[],
                recommended_action="Decompose task into smaller sub-tasks",
                details={
                    "pattern_type": error_type,
                },
            )

    # Check for missing info (might need research)
    for pattern, error_type in MISSING_INFO_PATTERNS:
        if re.search(pattern, combined_errors, re.IGNORECASE):
            # Generate research queries based on the error
            queries = _generate_research_queries(errors, error_type)

            return ClassificationResult(
                failure_type=FailureType.MISSING_INFO,
                confidence=0.70,
                reason=f"Missing information or documentation: {error_type}",
                research_queries=queries,
                recommended_action="Research the correct API/approach",
                details={
                    "pattern_type": error_type,
                },
            )

    # Check for bad assumptions
    for pattern, error_type in BAD_ASSUMPTIONS_PATTERNS:
        if re.search(pattern, combined_errors, re.IGNORECASE):
            queries = _generate_research_queries(errors, error_type)

            return ClassificationResult(
                failure_type=FailureType.BAD_ASSUMPTIONS,
                confidence=0.65,
                reason=f"Approach may be fundamentally incorrect: {error_type}",
                research_queries=queries,
                recommended_action="Research alternative approaches and restructure",
                details={
                    "pattern_type": error_type,
                },
            )

    return None


def _generate_research_queries(errors: list[str], error_type: str) -> list[str]:
    """Generate research queries based on error patterns."""
    queries = []
    combined = " ".join(errors)

    # Extract key terms from errors
    if error_type == "unknown_attribute":
        match = re.search(r"has no attribute ['\"](\w+)['\"]", combined)
        if match:
            attr = match.group(1)
            queries.append(f"Python {attr} attribute alternative replacement")

    elif error_type == "api_mismatch":
        # Try to extract function/method name
        match = re.search(
            r"(\w+)\(\).*unexpected keyword|(\w+)\(\).*positional arguments",
            combined,
        )
        if match:
            func = match.group(1) or match.group(2)
            queries.append(f"Python {func} function signature parameters 2026")

    elif error_type == "deprecated_api":
        match = re.search(r"(\w+).*deprecated", combined, re.IGNORECASE)
        if match:
            api = match.group(1)
            queries.append(f"{api} deprecated replacement alternative 2026")

    elif error_type == "assertion_failed":
        queries.append("Python test assertion best practices common failures")

    elif error_type in ("type_mismatch", "value_error"):
        queries.append("Python type error common causes and solutions")

    # Generic query if nothing specific
    if not queries:
        # Extract any error class names
        error_classes = re.findall(r"(\w+Error|\w+Exception)", combined)
        if error_classes:
            queries.append(f"Python {error_classes[0]} common causes solutions")
        else:
            queries.append("Python common coding errors and solutions")

    return queries


def check_repeated_errors(error_history: list[dict]) -> tuple[bool, Optional[str]]:
    """
    Check if the same error is repeating.

    Args:
        error_history: List of error records with 'error_msg' keys

    Returns:
        (is_repeated, repeated_error_pattern)
    """
    if len(error_history) < REPEATED_SAME_ERROR_THRESHOLD:
        return False, None

    # Normalize errors for comparison
    def normalize_error(msg: str) -> str:
        if not msg:
            return ""
        # Remove line numbers, file paths, memory addresses
        msg = re.sub(r"line \d+", "line X", msg)
        msg = re.sub(r"0x[0-9a-fA-F]+", "0xXXX", msg)
        msg = re.sub(r"/[^\s]+/", "/PATH/", msg)
        return msg.lower().strip()[:200]

    recent_errors = [
        normalize_error(e.get("error_msg", "")) for e in error_history[-5:]
    ]
    recent_errors = [e for e in recent_errors if e]

    if len(recent_errors) < REPEATED_SAME_ERROR_THRESHOLD:
        return False, None

    # Check if any error appears multiple times
    from collections import Counter

    error_counts = Counter(recent_errors)
    most_common = error_counts.most_common(1)

    if most_common and most_common[0][1] >= REPEATED_SAME_ERROR_THRESHOLD:
        return True, most_common[0][0]

    return False, None


def analyze_task_complexity(task: Task) -> dict:
    """
    Analyze if a task might be too complex.

    Args:
        task: Task object from database

    Returns:
        Dict with complexity analysis
    """
    complexity_score = 0
    reasons = []

    # Check number of steps
    steps = task.steps or []
    if len(steps) > 10:
        complexity_score += 3
        reasons.append(f"Many implementation steps ({len(steps)})")
    elif len(steps) > 5:
        complexity_score += 1
        reasons.append(f"Multiple steps ({len(steps)})")

    # Check dependencies
    deps = task.depends_on or []
    if len(deps) > 5:
        complexity_score += 2
        reasons.append(f"Many dependencies ({len(deps)})")
    elif len(deps) > 2:
        complexity_score += 1
        reasons.append(f"Multiple dependencies ({len(deps)})")

    # Check description length (proxy for complexity)
    description = task.description or ""
    if len(description) > 500:
        complexity_score += 2
        reasons.append("Long description suggesting complex requirements")
    elif len(description) > 200:
        complexity_score += 1
        reasons.append("Detailed description")

    # Check for complexity keywords
    complexity_keywords = [
        "complex",
        "multiple",
        "various",
        "all",
        "every",
        "complete",
        "full",
    ]
    desc_lower = description.lower()
    keyword_count = sum(1 for kw in complexity_keywords if kw in desc_lower)
    if keyword_count >= 3:
        complexity_score += 2
        reasons.append("Multiple complexity keywords in description")
    elif keyword_count >= 1:
        complexity_score += 1

    return {
        "complexity_score": complexity_score,
        "is_complex": complexity_score >= 4,
        "should_decompose": complexity_score >= 6,
        "reasons": reasons,
    }


def classify_failure(
    task: Task,
    error_history: list[dict],
    deps_status: dict,
) -> ClassificationResult:
    """
    Comprehensive failure classification combining pattern matching and analysis.

    Args:
        task: The Task object from database
        error_history: List of error records from escalation state
        deps_status: Dict mapping dep_id -> bool (completed)

    Returns:
        ClassificationResult with classification and recommendations
    """
    # Extract error messages
    errors = [e.get("error_msg", "") for e in error_history if e.get("error_msg")]

    # Check for repeated same error
    is_repeated, repeated_pattern = check_repeated_errors(error_history)

    # Try pattern-based classification first
    pattern_result = classify_by_patterns(errors)

    # Analyze complexity
    complexity = analyze_task_complexity(task)

    # Decision logic

    # 1. If same error keeps repeating, might be wrong approach
    if is_repeated and pattern_result:
        # Repeated errors often indicate wrong assumptions or missing info
        if pattern_result.failure_type == FailureType.WRONG_INFRA:
            return pattern_result  # Infrastructure issues are definitive
        else:
            # Upgrade to BAD_ASSUMPTIONS if repeating
            return ClassificationResult(
                failure_type=FailureType.BAD_ASSUMPTIONS,
                confidence=0.80,
                reason=f"Same error repeating: {repeated_pattern[:100]}...",
                research_queries=pattern_result.research_queries
                or _generate_research_queries(errors, "repeated"),
                recommended_action="Research alternative approaches",
                details={
                    "repeated_error": repeated_pattern,
                    "original_classification": pattern_result.failure_type.value,
                },
            )

    # 2. If pattern classification found something, use it
    if pattern_result:
        # But check if complexity is also an issue
        if complexity["should_decompose"]:
            return ClassificationResult(
                failure_type=FailureType.TOO_BIG,
                confidence=max(pattern_result.confidence, 0.75),
                reason=f"Task is complex ({complexity['reasons']}) and has errors",
                research_queries=[],
                recommended_action="Decompose into smaller tasks before continuing",
                details={
                    "complexity": complexity,
                    "also_has": pattern_result.failure_type.value,
                },
            )
        return pattern_result

    # 3. Check complexity alone
    if complexity["should_decompose"]:
        return ClassificationResult(
            failure_type=FailureType.TOO_BIG,
            confidence=0.70,
            reason=f"Task appears too complex: {', '.join(complexity['reasons'])}",
            research_queries=[],
            recommended_action="Decompose into smaller sub-tasks",
            details={"complexity": complexity},
        )

    # 4. Default to needs_research if we have errors but can't classify
    if errors:
        # Generate generic research queries from the errors
        queries = []
        for err in errors[-3:]:
            if err:
                # Extract key terms
                words = re.findall(r"\b[A-Z][a-z]+(?:Error|Exception|Failure)?\b", err)
                if words:
                    queries.append(f"Python {' '.join(words[:3])} error solution")

        return ClassificationResult(
            failure_type=FailureType.NEEDS_RESEARCH,
            confidence=0.50,
            reason="Unable to classify error pattern, research may help",
            research_queries=queries
            or ["Python common coding errors debugging techniques"],
            recommended_action="Research the error and potential solutions",
            details={"unclassified_errors": errors[-3:]},
        )

    # 5. No errors recorded - might be a silent failure
    return ClassificationResult(
        failure_type=FailureType.MISSING_INFO,
        confidence=0.40,
        reason="Task failed without clear error messages",
        research_queries=[f"How to implement {task.title[:50]}"],
        recommended_action="Research implementation approach",
        details={"task_id": task.id},
    )


def generate_diagnosis_prompt(
    task: Task,
    error_history: list[dict],
    classification: ClassificationResult,
) -> str:
    """
    Generate a prompt for LLM-based diagnosis to refine classification.

    Args:
        task: The task being diagnosed
        error_history: Error records
        classification: Initial classification result

    Returns:
        Prompt string for diagnosis
    """
    errors_text = "\n".join(
        [
            f"- {e.get('timestamp', 'unknown')}: {e.get('error_msg', 'no message')[:300]}"
            for e in error_history[-5:]
        ]
    )

    return f"""Analyze why this task is failing repeatedly and determine the root cause.

TASK:
ID: {task.spec_id}
Title: {task.title}
Description: {task.description or 'No description'}
Steps: {task.steps or []}
Dependencies: {task.depends_on or []}

RECENT ERRORS:
{errors_text}

INITIAL CLASSIFICATION:
Type: {classification.failure_type.value}
Confidence: {classification.confidence:.0%}
Reason: {classification.reason}

Analyze the errors and determine which category best fits:

1. TOO_BIG - Task needs to be broken into smaller parts
2. MISSING_INFO - Need to research documentation/APIs
3. WRONG_INFRA - Missing packages/tools (needs user intervention)
4. BAD_ASSUMPTIONS - Fundamental approach is wrong
5. NEEDS_RESEARCH - Need specific technical research

Respond with:
- CATEGORY: (one of the above)
- CONFIDENCE: (0-100%)
- REASON: (why this category)
- RESEARCH_QUERIES: (if applicable, list of search queries)
- RECOMMENDED_ACTION: (what to do next)
"""
