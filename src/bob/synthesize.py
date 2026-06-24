"""bob.synthesize — retry-aware acceptance-criteria synthesizer.

Public entry-point for spec synthesis with aggressive retry on transient
upstream API 400/empty-response errors (see bob.spec_synthesizer for
implementation details).

Root cause addressed: the shared upstream API key intermittently returns HTTP
400 ("Application 'Claude Code' (Production Restricted) is being deprecated;
subsequent requests will continue to work in the meantime"). The claude CLI
exits in ~1 second with EMPTY assistant text on this 400 and does NOT retry.
A single spawn attempt silently falls back to thin deterministic ACs (~0.75),
below the 0.85 gate, causing every feature in a burst window to fail synthesis.

The LLM spawn is wrapped in an aggressive retry loop (default 40 attempts,
env-tunable BOB_SYNTH_MAX_ATTEMPTS) with exponential backoff (2, 4, 8, 16, 32
seconds, capped at 60s) so a synthesis pass can outlast a multi-minute upstream
400 burst. Each retry attempt is logged so transient upstream bursts are
observable, not silent.

Public API:
  synthesize_for_feature   — async; spawns LLM with retry, returns list[str]|None
  score_gate_loop          — async; re-synthesizes until composite score >= threshold
  ScoreGateReport          — dataclass returned by score_gate_loop
  deterministic_fallback   — sync; builds fallback criteria without LLM
"""
from __future__ import annotations

from bob.spec_synthesizer import (
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

__all__ = [
    "ScoreGateReport",
    "build_retry_feedback_prompt",
    "deterministic_fallback",
    "deterministic_fallback_spec",
    "detect_integration_targets",
    "ensure_integration_criterion",
    "find_placeholder_features",
    "inject_boundary_and_error_acs",
    "is_placeholder",
    "iter_features",
    "parse_criteria_response",
    "sanitize_spec_file",
    "sanitize_spec_file_with_gate_loop",
    "score_gate_loop",
    "score_gate_threshold_from_env",
    "score_synthesized_acs",
    "synthesize_for_feature",
    "synthesize_with_score_gate",
]
