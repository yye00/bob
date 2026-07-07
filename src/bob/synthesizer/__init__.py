"""bob.synthesizer — retry-aware acceptance-criteria synthesizer.

This module is the canonical entry-point for spec synthesis with aggressive
retry on transient upstream API 400/empty-response errors.

Root cause addressed: the shared upstream API key intermittently returns HTTP
400 ("Application 'Claude Code' (Production Restricted) is being deprecated;
subsequent requests will continue to work in the meantime"). The claude CLI
exits in ~1 second with EMPTY assistant text on this 400 and does NOT retry it.
A single spawn attempt silently falls back to thin deterministic ACs (~0.75),
below the 0.85 gate, causing every feature in a burst window to fail synthesis.

This module wraps the LLM spawn in an aggressive retry loop (default 40
attempts, env-tunable BOB_SYNTH_MAX_ATTEMPTS) with exponential backoff
(2, 4, 8, 16, 32 seconds, capped at 60s) so a synthesis pass can outlast a
multi-minute upstream 400 burst. Each retry attempt is logged so transient
upstream bursts are observable, not silent.

Public API (mirrors bob.spec_synthesizer via bob.synthesize):
  synthesize_for_feature   — async; spawns LLM with retry, returns list[str]|None
  score_gate_loop          — async; re-synthesizes until composite score >= threshold
  ScoreGateReport          — dataclass returned by score_gate_loop
  deterministic_fallback   — sync; builds fallback criteria without LLM
"""
from __future__ import annotations

from bob.synthesize import (
    ScoreGateReport,
    _DEFAULT_MAX_RETRIES,
    _DEFAULT_SPEC_QUALITY_THRESHOLD,
    build_retry_feedback_prompt,
    deterministic_fallback,
    deterministic_fallback_spec,
    detect_integration_targets,
    ensure_integration_criterion,
    find_placeholder_features,
    inject_boundary_and_error_acs,
    is_placeholder,
    iter_features,
    parse_criteria_response,
    sanitize_spec_file,
    sanitize_spec_file_with_gate_loop,
    score_gate_loop,
    score_gate_threshold_from_env,
    score_synthesized_acs,
    synthesize_for_feature,
    synthesize_with_score_gate,
)
from bob.spec_synthesizer import (
    _ensure_boundary_and_error_coverage,
    should_emit_function_ac,
    synthesize_with_retry,
)
from tools.spec_quality_score import (
    is_code_shaped_token,
    filter_code_shaped_surfaces,
    emit_file_exists_acs,
)
from bob.synthesizer_boundary_error_ac_injector import (
    extract_criterion_text_from_object_format,
    inject_boundary_and_error_acs as _inject_boundary_and_error_acs_new,
)
from bob.skip_ratio_gate import (
    classify_skip_reason,
    emit_skip_ratio_bound,
    gates_on_suite_metric,
)

import logging as _logging

_logger = _logging.getLogger(__name__)


def handle_exponential_backoff(
    attempt: int,
    *,
    title: str = "",
    error_sig: str = "",
    cap: int = 60,
    rate_limit_cap: int = 120,
) -> float:
    """Compute the exponential backoff delay for a synthesizer retry attempt.

    Used to outlast transient upstream HTTP 400 bursts (shared API key
    rate-limiting). Returns the sleep duration in seconds and emits a WARNING
    log so upstream bursts are observable, not silent.

    Standard backoff: min(2**attempt, cap) seconds.
    Rate-limited backoff: 30s floor + exponential, capped at rate_limit_cap.
    """
    _RATE_LIMIT_SIGS = (
        "429", "resource_exhausted", "resourceexhausted", "rate limit",
        "rate-limit", "ratelimit", "quota", "too many requests",
        "overloaded", "503", "unavailable", "request limit",
    )
    err_lower = (error_sig or "").lower()
    rate_limited = any(s in err_lower for s in _RATE_LIMIT_SIGS)

    if rate_limited:
        delay = float(min(30 + 2 ** attempt, rate_limit_cap))
        _logger.warning(
            "synthesizer RATE-LIMITED for %r (attempt %d) — backing off %.0fs",
            title, attempt, delay,
        )
    else:
        delay = float(min(2 ** attempt, cap))
        _logger.warning(
            "synthesizer returned empty for %r (attempt %d) — retrying in %.0fs",
            title, attempt, delay,
        )
    return delay


# Canonical aliases: ACs for this feature require both names.
inject_boundary_error_criteria = inject_boundary_and_error_acs
inject_boundary_and_error_criteria = inject_boundary_and_error_acs
inject_boundary_error_acs = inject_boundary_and_error_acs

# AC alias: "Function defined: bob.synthesizer.inject_missing_coverage"
# inject_missing_coverage is the canonical public name for the boundary/error
# AC injection function — ensures coverage gaps don't drive composite to 0.0.
inject_missing_coverage = inject_boundary_and_error_acs

__all__ = [
    "ScoreGateReport",
    "_ensure_boundary_and_error_coverage",
    "build_retry_feedback_prompt",
    "classify_skip_reason",
    "emit_skip_ratio_bound",
    "gates_on_suite_metric",
    "deterministic_fallback",
    "deterministic_fallback_spec",
    "detect_integration_targets",
    "ensure_integration_criterion",
    "emit_file_exists_acs",
    "extract_criterion_text_from_object_format",
    "find_placeholder_features",
    "handle_exponential_backoff",
    "inject_boundary_and_error_acs",
    "inject_boundary_and_error_criteria",
    "inject_boundary_error_acs",
    "inject_boundary_error_criteria",
    "inject_missing_coverage",
    "is_placeholder",
    "iter_features",
    "parse_criteria_response",
    "sanitize_spec_file",
    "sanitize_spec_file_with_gate_loop",
    "score_gate_loop",
    "score_gate_threshold_from_env",
    "score_synthesized_acs",
    "synthesize_for_feature",
    "synthesize_with_retry",
    "synthesize_with_score_gate",
]
