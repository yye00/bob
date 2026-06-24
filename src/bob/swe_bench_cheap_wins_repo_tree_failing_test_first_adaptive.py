"""SWE-Bench cheap wins — repo tree, failing-test-first, adaptive edit mode, mutation-pass check.

Feature b9dac9b9: Four leaderboard-validated brownfield prompt/edit directives wired through the
worker-spawn path, each togglable via feature YAML (defaults ON).

Research basis:
- Anthropic SWE-Bench scaffold (Sonnet 4.5 77.2%, high-comp 82.0%)
- Agentless 1.5 (50.8%)
- SWE-Edit NeurIPS 2025 (+2.1% accuracy / -17.9% cost)
- ICSE 2026 false-pass study (12-22% of "passing" patches are logically wrong)

(A) repo_tree — prepend capped directory tree to worker prompt (200-line cap)
    Addresses "right file wrong abstraction" and "wrong file" failure modes.

(B) failing_repro_test — STANDING DIRECTIVE: write failing test first (TDD)
    Anthropic's own +pp prompt addendum. Toggleable via feature.skip_repro_test.

(C) EDIT_MODE — adaptive: string-replace default, whole-file rewrite when sites>3 or span>40
    SWE-Edit finding: switch modes based on edit complexity.

(D) WEAK_TEST_DETECTED — mutation-pass check: flip constant/boolean, re-run, flag if still passes
    ICSE 2026: after test-pass, mutate code; if test still passes, flag as weak.

Integration: bob.orchestrator.run_loop (imported as integration AC).

Public API
----------
swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(prompt, workspace, feature, ...)
    Main entry point: applies all four cheap wins, returns (augmented_prompt, metadata).

apply_repo_tree(workspace, max_lines)
    Generate the capped repo tree string for a workspace.

apply_failing_repro_test_directive(prompt, feature)
    Inject the failing-repro-test standing directive if applicable.

select_adaptive_edit_mode(edit_site_count, edit_span)
    Choose between 'replace' and 'rewrite' based on edit complexity.

run_weak_test_check(test_command, workspace, feature_id, ...)
    Check if a test still passes after a trivial mutation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from bob.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    build_repo_tree,
    check_mutation_pass,
    compute_edit_mode,
    emit_edit_mode_event,
    emit_weak_test_event,
    inject_failing_repro_test_directive,
    inject_repo_tree_into_prompt,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)

logger = logging.getLogger(__name__)


def apply_repo_tree(
    workspace: str | Path,
    max_lines: int = 200,
) -> str:
    """Generate the capped repo tree string for a workspace.

    Delegates to bob.dispatch.build_repo_tree. Prepends a capped
    directory tree (200-line default) to address localization failure modes.

    Args:
        workspace: Project workspace path.
        max_lines: Maximum tree lines before truncation (default 200).

    Returns:
        Tree string with optional "… (N more)" trailer when truncated.
    """
    return build_repo_tree(workspace, max_lines=max_lines)


def apply_failing_repro_test_directive(
    prompt: str,
    feature: Any,
) -> tuple[str, bool]:
    """Inject the failing-repro-test standing directive into prompt if applicable.

    Checks whether the feature has skip_repro_test=True or all structural ACs.
    Returns the (possibly augmented) prompt and whether the directive was injected.

    Args:
        prompt:  Base worker prompt text.
        feature: Feature object used for toggle checks.

    Returns:
        Tuple of (augmented_prompt, was_injected).
    """
    if should_inject_repro_test_directive(feature):
        return inject_failing_repro_test_directive(prompt), True
    return prompt, False


def select_adaptive_edit_mode(
    edit_site_count: int,
    edit_span: int,
) -> EditModeDecision:
    """Choose between 'replace' and 'rewrite' based on edit complexity.

    Delegates to bob.dispatch.select_edit_mode. Uses SWE-Edit (NeurIPS 2025)
    thresholds: string-replace is the default; switch to whole-file rewrite
    when edit_site_count > 3 OR edit_span > 40 lines.

    Args:
        edit_site_count: Number of distinct edit locations from the localizer.
        edit_span:       Total line span covered by edits.

    Returns:
        EditModeDecision with mode ('replace' or 'rewrite'), sites, and span.
    """
    return select_edit_mode(edit_site_count, edit_span)


def run_weak_test_check(
    test_command: list[str],
    workspace: str | Path,
    feature_id: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> bool:
    """Check if a test still passes after a trivial mutation.

    Delegates to bob.dispatch.run_mutation_pass_check. Returns True if the
    test STILL passes after mutation, indicating a likely under-specified test.
    Emits WEAK_TEST_DETECTED when True.

    ICSE 2026 finding: 12-22% of "passing" patches are logically wrong.
    Cost: 1 extra test run per feature. Worth it.

    Args:
        test_command: pytest / unittest command to run.
        workspace:    Project workspace directory.
        feature_id:   Feature ID for telemetry correlation.
        env:          Optional extra environment variables.
        timeout:      Subprocess timeout in seconds.

    Returns:
        True if the mutated test still passes (weak test); False if it fails
        (test is adequately specified).
    """
    return run_mutation_pass_check(
        test_command, workspace, feature_id, env=env, timeout=timeout
    )


def swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
    prompt: str,
    workspace: str | Path,
    feature: Any,
    *,
    edit_site_count: int = 0,
    edit_span: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Apply all four F-R7-609 SWE-Bench cheap wins to a worker prompt.

    This is the canonical entry point for the feature. It applies:
    (A) repo_tree injection — prepend capped directory tree
    (B) failing_repro_test directive — STANDING DIRECTIVE: write failing test first
    (C) EDIT_MODE selection — adaptive string-replace vs whole-file rewrite
    (D) Metadata for WEAK_TEST_DETECTED check — telemetry setup for mutation pass

    Each win is toggleable via feature attributes (defaults ON):
    - feature.skip_repo_tree = True  → skip (A)
    - feature.skip_repro_test = True → skip (B)

    Args:
        prompt:          Original worker prompt text.
        workspace:       Project workspace path.
        feature:         Feature object (read-only) used for toggle checks.
        edit_site_count: Number of edit sites from the localizer (F-R7-600).
        edit_span:       Total line span of edits from the localizer.

    Returns:
        Tuple of (augmented_prompt, metadata_dict). metadata_dict contains:
          - repo_tree_injected (bool)
          - failing_repro_test_injected (bool)
          - edit_mode (dict with event, mode, sites, span)
    """
    augmented_prompt, metadata = apply_cheap_wins(
        prompt,
        workspace,
        feature,
        edit_site_count=edit_site_count,
        edit_span=edit_span,
    )

    logger.info(
        json.dumps({
            "event": "SWE_BENCH_CHEAP_WINS_APPLIED",
            "feature_id": getattr(feature, "id", None),
            "repo_tree_injected": metadata.get("repo_tree_injected"),
            "failing_repro_test_injected": metadata.get("failing_repro_test_injected"),
            "edit_mode": metadata.get("edit_mode", {}).get("mode"),
        })
    )

    return augmented_prompt, metadata


__all__ = [
    "apply_failing_repro_test_directive",
    "apply_repo_tree",
    "run_weak_test_check",
    "select_adaptive_edit_mode",
    "swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive",
    "EditModeDecision",
]
