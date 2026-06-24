"""Bidirectional Requirements Traceability Matrix (RTM) — bob.spec_coverage.

Forward (AC -> test -> code-region) and backward (code-region -> AC)
traceability as a first-class artifact. tools/spec_coverage.py emits
rtm.json and rtm.html. spec_coverage_pct halt-gate at 0.80. New functions
in a commit without an AC link are flagged untraced_implementation.

This module re-exports the canonical RTM functions from tools.spec_coverage
under the bob.spec_coverage namespace required by the AC.
"""

from __future__ import annotations

from tools.spec_coverage import (  # noqa: F401
    build_rtm,
    check_halt_gate,
    check_spec_coverage_gate,
    check_untraced_implementation,
    compute_ac_record,
    compute_spec_coverage_pct,
    emit_rtm,
    emit_rtm_artifacts,
    emit_rtm_html,
    emit_rtm_json,
    flag_untraced_implementation,
    generate_rtm,
    halt_gate_fires_at_80,
    handle_zero_acs,
    never_divides_by_zero_on_empty_acs,
    validate_ac_traceability,
    validate_spec_coverage_pct,
    verify_traceability,
)


def generate_rtm_json(
    rtm,
    *,
    runs_dir,
    feature_id: str,
):
    """Write runs/<feature_id>/rtm.json and return the output path.

    AC-required entry point on bob.spec_coverage namespace.
    Delegates to tools.spec_coverage.emit_rtm_json.
    """
    return emit_rtm_json(rtm, runs_dir=runs_dir, feature_id=feature_id)


def generate_rtm_html(
    rtm,
    *,
    runs_dir,
    feature_id: str,
):
    """Write runs/<feature_id>/rtm.html and return the output path.

    AC-required entry point on bob.spec_coverage namespace.
    Delegates to tools.spec_coverage.emit_rtm_html.
    """
    return emit_rtm_html(rtm, runs_dir=runs_dir, feature_id=feature_id)
