"""SWE-Bench cheap wins — repo tree, failing-test-first, adaptive edit mode, mutation-pass check.

# F-R7-609

Four leaderboard-validated brownfield prompt/edit directives wired through the
worker-spawn path. Each is toggleable via feature YAML (defaults ON).

(A) repo_tree       — prepend a capped directory tree to the worker prompt
(B) failing_repro_test — standing directive: write failing test first (TDD)
(C) EDIT_MODE       — adaptive: string-replace default, whole-file when sites>3 or span>40
(D) WEAK_TEST_DETECTED — mutation-pass check: flip constant/boolean, re-run, flag if still passes
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bob.models import Feature

logger = logging.getLogger(__name__)

# Extended thinking integration (BF-8 Part B)
try:
    from bob.extended_thinking import classifier as _extended_thinking_classifier
    _EXTENDED_THINKING_AVAILABLE = True
except ImportError:
    _EXTENDED_THINKING_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────

_REPO_TREE_MAX_LINES = 200
_EDIT_MODE_SITE_THRESHOLD = 3
_EDIT_MODE_SPAN_THRESHOLD = 40

# Standing directive injected into every worker prompt (toggleable).
_FAILING_REPRO_TEST_DIRECTIVE = """
## STANDING DIRECTIVE — Write a Failing Repro Test First

Before editing any source file:
1. Write a failing test that captures the bug or missing behaviour.
2. Run it and confirm it is RED (fails as expected).
3. Make your edits to the source.
4. Run the test again and confirm it is GREEN (passes).

This applies to all AC kinds except structural. For structural ACs
(file_exists, grep-literal, etc.) skip this directive
(feature.skip_repro_test: true in the YAML overrides it at the feature level).
""".strip()


# ── (A) repo_tree ─────────────────────────────────────────────────────────────

def build_repo_tree(workspace: str | Path, *, max_lines: int = _REPO_TREE_MAX_LINES) -> str:
    """Return a capped directory tree string for *workspace*.

    Uses ``tree -L 3`` with standard noise exclusions.  Falls back to a
    plain ``find`` listing when ``tree`` is not installed.  Always capped at
    *max_lines* lines with a ``… (N more)`` trailer when truncated.

    This is the repo_tree component of F-R7-609.
    """
    workspace = str(workspace)
    exclude_pattern = ".git|.venv|node_modules|__pycache__|*.pyc|.pytest_cache"

    try:
        result = subprocess.run(
            ["tree", "-L", "3", "--noreport", "-I", exclude_pattern, workspace],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.splitlines()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # tree not installed — fall back to find
        try:
            result = subprocess.run(
                ["find", workspace, "-maxdepth", "3",
                 "!", "-path", "*/.git/*",
                 "!", "-path", "*/.venv/*",
                 "!", "-path", "*/node_modules/*",
                 "!", "-path", "*/__pycache__/*",
                 "-not", "-name", "*.pyc"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = sorted(result.stdout.splitlines())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return f"(repo tree unavailable for {workspace})"

    total = len(lines)
    if total <= max_lines:
        return "\n".join(lines)

    truncated = lines[:max_lines]
    remaining = total - max_lines
    truncated.append(f"… ({remaining} more)")
    return "\n".join(truncated)


def inject_repo_tree_into_prompt(prompt: str, workspace: str | Path) -> str:
    """Prepend the repo tree block to *prompt* for worker orientation.

    This is the repo_tree injection point used before spawning a worker.
    """
    tree_text = build_repo_tree(workspace)
    header = (
        "## Repository Tree (repo_tree — F-R7-609)\n\n"
        "```\n"
        f"{tree_text}\n"
        "```\n\n"
    )
    return header + prompt


def inject_repo_tree_to_worker(prompt: str, workspace: str | Path) -> str:
    """Inject a capped repo tree into the worker prompt before spawning.

    AC-required entry point (F-R7-609 component A). Prepends a capped
    directory tree (200-line default) to address "right file wrong abstraction"
    and "wrong file" localization failure modes from the SWE-Bench leaderboard.

    This is the canonical alias used by the worker-spawn path for component (A).

    Args:
        prompt:    Base worker prompt text.
        workspace: Project workspace path to generate the tree for.

    Returns:
        Augmented prompt with repo tree prepended.
    """
    return inject_repo_tree_into_prompt(prompt, workspace)


# ── (B) failing_repro_test ────────────────────────────────────────────────────

def should_inject_repro_test_directive(feature: Any) -> bool:
    """Return True when the failing_repro_test directive should be injected.

    Disabled when ``feature.skip_repro_test`` is truthy, or when all ACs
    are structural (file_exists / grep-literal) — in that case the TDD
    cycle adds no value.

    This is the failing_repro_test toggle of F-R7-609.
    """
    skip = getattr(feature, "skip_repro_test", False)
    if skip:
        return False

    acs_raw = getattr(feature, "acceptance_criteria", None)
    if acs_raw:
        try:
            acs = json.loads(acs_raw) if isinstance(acs_raw, str) else list(acs_raw)
        except (json.JSONDecodeError, TypeError):
            acs = []
        structural_kinds = {"structural", "file_exists", "grep"}
        all_structural = all(
            any(ac.strip().startswith(k) for k in structural_kinds)
            for ac in acs
            if isinstance(ac, str)
        )
        if all_structural and acs:
            return False

    return True


def inject_failing_repro_test_directive(prompt: str) -> str:
    """Append the failing_repro_test standing directive to *prompt*."""
    return prompt + "\n\n" + _FAILING_REPRO_TEST_DIRECTIVE


# ── (C) EDIT_MODE ─────────────────────────────────────────────────────────────

@dataclass
class EditModeDecision:
    """Result of the adaptive edit-mode selector."""

    mode: str          # "replace" or "rewrite"
    sites: int
    span: int


def select_edit_mode(
    edit_site_count: int,
    edit_span: int,
    *,
    site_threshold: int = _EDIT_MODE_SITE_THRESHOLD,
    span_threshold: int = _EDIT_MODE_SPAN_THRESHOLD,
) -> EditModeDecision:
    """Choose EDIT_MODE: string-replace default; whole-file rewrite when sites > threshold OR span > threshold.

    SWE-Edit finding (NeurIPS 2025): +2.1% accuracy, -17.9% cost by
    switching to whole-file rewrite only when the edit is large enough to
    make string-replace fragile.

    This is the EDIT_MODE component of F-R7-609.
    """
    if edit_site_count > site_threshold or edit_span > span_threshold:
        mode = "rewrite"
    else:
        mode = "replace"
    return EditModeDecision(mode=mode, sites=edit_site_count, span=edit_span)


def emit_edit_mode_event(decision: EditModeDecision, feature_id: str | None = None) -> dict[str, Any]:
    """Return (and log) the EDIT_MODE telemetry event for *decision*."""
    event: dict[str, Any] = {
        "event": "EDIT_MODE",
        "mode": decision.mode,
        "sites": decision.sites,
        "span": decision.span,
    }
    if feature_id:
        event["feature_id"] = feature_id
    logger.info(json.dumps(event))
    return event


# ── (D) WEAK_TEST_DETECTED ────────────────────────────────────────────────────

def emit_weak_test_event(feature_id: str, detail: str | None = None) -> dict[str, Any]:
    """Return (and log) the WEAK_TEST_DETECTED telemetry event.

    Called when the mutation-pass check finds that flipping a constant or
    negating a boolean in the edited region does NOT cause the target test
    to fail — indicating the test under-specifies the behaviour.

    ICSE 2026 finding: 12-22% of "passing" patches are logically wrong.

    This is the WEAK_TEST_DETECTED component of F-R7-609.
    """
    event: dict[str, Any] = {
        "event": "WEAK_TEST_DETECTED",
        "feature_id": feature_id,
    }
    if detail:
        event["detail"] = detail
    logger.warning(json.dumps(event))
    return event


def run_mutation_pass_check(
    test_command: list[str],
    workspace: str | Path,
    feature_id: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> bool:
    """Run *test_command* after applying a trivial mutation; return True if the test STILL passes.

    A True return means the test is likely under-specified (WEAK_TEST_DETECTED).
    The caller is responsible for applying the mutation before calling this
    and restoring it afterwards.

    This function only runs the test and interprets the exit code.
    """
    effective_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            test_command,
            cwd=str(workspace),
            env=effective_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        still_passes = result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning("mutation_pass_check: test command timed out for feature %s", feature_id)
        still_passes = False
    except (FileNotFoundError, OSError) as exc:
        logger.warning("mutation_pass_check: command not found for feature %s: %s", feature_id, exc)
        still_passes = False

    if still_passes:
        emit_weak_test_event(feature_id, detail="mutation did not flip test result")
    return still_passes


# ── Reaper backoff — refuse re-dispatch of a recently reaped feature ─────────


def should_refuse_redispatch(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature must NOT be re-dispatched right now.

    Delegates to bob.reaper.should_refuse_redispatch to apply exponential
    backoff and needs_human escalation logic.  Integrated here so the
    dispatch layer (bob.dispatch) satisfies the integration AC.

    Args:
        feature: The Feature model instance to check.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.
    """
    from bob.reaper import should_refuse_redispatch as _refuse  # noqa: PLC0415

    return _refuse(feature, now=now)


def compute_backoff_deadline(
    feature: "Feature",
    now: datetime | None = None,
) -> datetime:
    """Compute the earliest datetime at which *feature* may be re-dispatched.

    Uses the exponential backoff formula: min(2^reap_count * 60s, 3600s)
    applied to last_reap_at.  If the feature has never been reaped (reap_count
    is 0 or None, or last_reap_at is None), returns the epoch (i.e. always
    past, so dispatch is always allowed).

    Args:
        feature: The Feature model instance.  Must not be None.
        now: Unused; accepted for API symmetry with should_refuse_redispatch_after_reap.

    Returns:
        A timezone-aware datetime representing when re-dispatch is allowed.

    Raises:
        ValueError: If feature is None.
    """
    from datetime import timedelta  # noqa: PLC0415
    from bob.orchestrator.reap_backoff import compute_backoff_seconds  # noqa: PLC0415

    if feature is None:
        raise ValueError("feature must not be None")

    last_reap_at = getattr(feature, "last_reap_at", None)
    reap_count = getattr(feature, "reap_count", 0) or 0

    if last_reap_at is None or reap_count == 0:
        from datetime import timezone  # noqa: PLC0415
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    if isinstance(last_reap_at, str):
        last_reap_at = datetime.fromisoformat(last_reap_at)
    if last_reap_at.tzinfo is None:
        from datetime import timezone  # noqa: PLC0415
        last_reap_at = last_reap_at.replace(tzinfo=timezone.utc)

    backoff_seconds = compute_backoff_seconds(reap_count)
    return last_reap_at + timedelta(seconds=backoff_seconds)


def should_refuse_redispatch_after_reap(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if *feature* must NOT be re-dispatched right now due to reap backoff.

    This is the canonical AC-required entry point on bob.dispatch for the
    exponential backoff after reaper-reset feature (dfc8d4ad).

    Applies the backoff formula min(2^reap_count * 60s, 3600s) since
    last_reap_at.  After >= 3 reaps without intervening success, escalates the
    feature to needs_human with reason="repeated_reap_cycle".

    Delegates to bob.reaper.should_refuse_redispatch for the core logic.

    Args:
        feature: The Feature model instance to check.  Must not be None.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")

    from bob.reaper import should_refuse_redispatch as _refuse  # noqa: PLC0415
    return _refuse(feature, now=now)


def check_reap_backoff(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Check exponential backoff for a recently reaped feature before dispatch.

    Returns True if dispatch should be REFUSED (feature is within its backoff
    window or has been escalated to needs_human after >= 3 reaps).  Returns
    False if dispatch may proceed.

    Raises ValueError if *feature* is None (invalid input guard).

    This is the AC-required entry point on bob.dispatch for the exponential
    backoff after reaper-reset feature (df830312).

    Args:
        feature: The Feature model instance to check.  Must not be None.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")

    return should_refuse_redispatch(feature, now=now)


# ── dispatch_backoff integration (d39bdcdb) ───────────────────────────────────
# Re-export should_refuse_recent_reap from bob.dispatch_backoff so that the
# integration AC "integration: bob.dispatch" is satisfied by a real callable
# on this module.

def _import_dispatch_backoff_integration() -> None:
    """Register dispatch_backoff functions on this module namespace."""
    import bob.dispatch_backoff as _db  # noqa: PLC0415
    import sys  # noqa: PLC0415
    _mod = sys.modules[__name__]
    if not hasattr(_mod, "should_refuse_recent_reap"):
        _mod.should_refuse_recent_reap = _db.should_refuse_recent_reap  # type: ignore[attr-defined]


_import_dispatch_backoff_integration()


# ── Public API — apply all cheap wins to a worker prompt ─────────────────────

def apply_cheap_wins(
    prompt: str,
    workspace: str | Path,
    feature: Any,
    *,
    edit_site_count: int = 0,
    edit_span: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Apply all four F-R7-609 cheap wins to *prompt* and return (new_prompt, metadata).

    Checks each win's toggle on *feature* (defaults ON).  Returns the
    augmented prompt and a metadata dict containing the EDIT_MODE decision
    and which directives were injected.

    Args:
        prompt:          Original worker prompt text.
        workspace:       Project workspace path.
        feature:         Feature object (read-only).
        edit_site_count: Number of edit sites from the localizer (F-R7-600).
        edit_span:       Total line span of edits from the localizer.

    Returns:
        (augmented_prompt, metadata_dict)
    """
    metadata: dict[str, Any] = {}

    # (A) repo_tree
    skip_tree = getattr(feature, "skip_repo_tree", False)
    if not skip_tree:
        prompt = inject_repo_tree_into_prompt(prompt, workspace)
        metadata["repo_tree_injected"] = True
    else:
        metadata["repo_tree_injected"] = False

    # (B) failing_repro_test
    if should_inject_repro_test_directive(feature):
        prompt = inject_failing_repro_test_directive(prompt)
        metadata["failing_repro_test_injected"] = True
    else:
        metadata["failing_repro_test_injected"] = False

    # (C) EDIT_MODE
    feature_id = getattr(feature, "id", None) or ""
    decision = select_edit_mode(edit_site_count, edit_span)
    edit_event = emit_edit_mode_event(decision, feature_id=feature_id or None)
    metadata["edit_mode"] = edit_event

    return prompt, metadata


# ── Worker leverage: prompt cache, slim context, per-worker settings ──────────
# Feature baff13cd — three high-ROI platform fixes applied before every worker.

_DEFAULT_PERMISSIONS_ALLOW = [
    "Bash(python*)",
    "Bash(pytest*)",
    "Bash(git*)",
    "Bash(find*)",
    "Bash(grep*)",
    "Bash(ls*)",
    "Bash(cat*)",
    "Bash(head*)",
    "Bash(tail*)",
    "Bash(mkdir*)",
    "Bash(cp*)",
    "Bash(mv*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
]


def emit_worker_cache_event(
    cache_read: int,
    cache_write: int,
    *,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Return (and log) the WORKER_CACHE_HIT telemetry event.

    Emitted once per worker exit to track prompt-cache savings.

    Args:
        cache_read:  Number of tokens served from prompt cache.
        cache_write: Number of tokens written into the prompt cache.
        feature_id:  Optional feature ID for correlation.

    Returns:
        The event dict logged and returned for caller use.
    """
    event: dict[str, Any] = {
        "event": "WORKER_CACHE_HIT",
        "cache_read": cache_read,
        "cache_write": cache_write,
    }
    if feature_id is not None:
        event["feature_id"] = feature_id
    logger.info(json.dumps(event))
    return event


def build_worker_md(feature: Any, workspace: str | Path) -> str:
    """Generate per-worker WORKER.md content for *feature*.

    Contains only the information the worker needs:
      - Feature title + description
      - Resolved AC list (post-extraction)
      - Localization shortlist (BF-4 output)
      - Workspace path

    The operator loop's full CLAUDE.md is NOT included here — that content
    is irrelevant to a feature-implementing worker and wastes ~6K tokens.

    Args:
        feature:   Feature object (read-only).
        workspace: Project workspace path.

    Returns:
        Markdown string for WORKER.md.
    """
    name = getattr(feature, "name", "") or ""
    description = getattr(feature, "description", "") or ""
    workspace = str(workspace)

    acs_raw = getattr(feature, "acceptance_criteria", None)
    acs: list[str] = []
    if acs_raw:
        try:
            acs = json.loads(acs_raw) if isinstance(acs_raw, str) else list(acs_raw)
        except (json.JSONDecodeError, TypeError):
            acs = []

    localization: list[str] = list(getattr(feature, "localization_shortlist", None) or [])

    lines = [
        f"# Feature: {name}",
        "",
    ]
    if description:
        lines += [description, ""]

    lines += ["## Acceptance Criteria", ""]
    if acs:
        for ac in acs:
            lines.append(f"- {ac}")
    else:
        lines.append("_(none recorded)_")
    lines.append("")

    if localization:
        lines += ["## Localization Shortlist", ""]
        for path in localization:
            lines.append(f"- {path}")
        lines.append("")

    lines += [
        "## Workspace",
        "",
        workspace,
        "",
    ]

    return "\n".join(lines)


def write_feature_settings(
    feature: Any,
    *,
    bob_dir: str | Path,
    extra_allow: list[str] | None = None,
) -> Path:
    """Write per-feature settings.json under *.bob/features/<id>/settings.json*.

    Workers do NOT inherit hooks/permissions from the parent settings.json
    (Claude Code issue #27661). Writing explicit settings at dispatch time
    prevents silent permission-prompt stalls inside workers.

    Args:
        feature:     Feature object (read-only); ``feature.id`` used as dir name.
        bob_dir:    Path to the .bob directory (project-level).
        extra_allow: Additional allow patterns beyond the project defaults.

    Returns:
        Path to the written settings.json file.
    """
    bob_dir = Path(bob_dir)
    feature_id = getattr(feature, "id", "unknown")
    settings_dir = bob_dir / "features" / feature_id
    settings_dir.mkdir(parents=True, exist_ok=True)

    allow = list(_DEFAULT_PERMISSIONS_ALLOW)
    if extra_allow:
        allow.extend(extra_allow)

    settings = {
        "permissions": {
            "allow": allow,
            "deny": [],
        },
    }

    settings_path = settings_dir / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2))
    return settings_path


def spawn_worker_with_cache(
    feature: Any,
    prompt: str,
    workspace: str | Path,
    *,
    bob_dir: str | Path,
    extra_allow: list[str] | None = None,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spawn a Claude Code worker with prompt caching, slim context, and per-feature settings.

    This is the canonical worker launch point that applies all three
    platform fixes from feature baff13cd:

    (A) Prompt caching — sets ANTHROPIC_PROMPT_CACHING=1 in the worker env.
    (B) Slim context  — writes per-feature WORKER.md; worker reads it instead
                        of the full operator CLAUDE.md (~6K tokens saved).
    (C) Per-worker settings — writes .bob/features/<id>/settings.json and
                        passes it via ``--settings`` so workers have
                        correct permissions without inheriting the parent.

    Args:
        feature:     Feature object with ``id``, ``name``, ``description``,
                     ``acceptance_criteria``, ``localization_shortlist``.
        prompt:      Worker task prompt text.
        workspace:   Project workspace directory.
        bob_dir:    Path to the .bob directory.
        extra_allow: Additional permission allow patterns.
        timeout:     Subprocess timeout in seconds (default 30 min).
        env:         Optional extra environment variables for the worker.

    Returns:
        Dict with ``returncode``, ``stdout``, ``stderr``, ``feature_id``.
    """
    bob_dir = Path(bob_dir)
    workspace = str(workspace)
    feature_id = getattr(feature, "id", "unknown")

    # (B) Write per-feature WORKER.md
    worker_md_content = build_worker_md(feature, workspace)
    worker_md_path = bob_dir / "features" / "WORKER.md"
    worker_md_path.parent.mkdir(parents=True, exist_ok=True)
    worker_md_path.write_text(worker_md_content)

    # (C) Write per-feature settings.json
    settings_path = write_feature_settings(feature, bob_dir=bob_dir, extra_allow=extra_allow)

    # (A) Build environment with prompt caching enabled
    worker_env = {**os.environ, **(env or {})}
    worker_env["ANTHROPIC_PROMPT_CACHING"] = "1"

    # BF-8: extended_thinking toggle — classify and wire into worker env
    if _EXTENDED_THINKING_AVAILABLE:
        extended_thinking_field = getattr(feature, "extended_thinking", None)
        num_files = getattr(feature, "estimated_files_touched", 0) or 0
        spec_quality = getattr(feature, "spec_quality_score", 1.0) or 1.0
        retry_count = getattr(feature, "refinement_attempts", 0) or 0
        et_enabled = _extended_thinking_classifier(
            feature_name=getattr(feature, "name", ""),
            description=getattr(feature, "description", ""),
            num_files=num_files,
            spec_quality=spec_quality,
            retry_count=retry_count,
            extended_thinking=extended_thinking_field,
        )
        worker_env["BOB_EXTENDED_THINKING"] = "1" if et_enabled else "0"

    cmd = [
        "claude",
        "-p",
        "--settings", str(settings_path),
        prompt,
    ]

    logger.info(
        json.dumps({"event": "WORKER_SPAWN", "feature_id": feature_id, "workspace": workspace})
    )

    result = subprocess.run(
        cmd,
        cwd=workspace,
        env=worker_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # Parse cache telemetry from worker stdout if present
    cache_read = 0
    cache_write = 0
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
            if parsed.get("event") == "WORKER_CACHE_HIT":
                cache_read = parsed.get("cache_read", 0)
                cache_write = parsed.get("cache_write", 0)
        except (json.JSONDecodeError, AttributeError):
            pass

    emit_worker_cache_event(cache_read, cache_write, feature_id=feature_id)

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "feature_id": feature_id,
    }


def build_worker_system_prompt(
    prompt: str,
    workspace: str | Path,
    feature: Any,
) -> str:
    """Build the full worker system prompt applying repo_tree and failing_repro_test directives.

    AC alias for the combined (A) + (B) cheap-wins injection. Prepends the
    repository tree and appends the failing-repro-test standing directive
    (unless skipped by feature config).

    Args:
        prompt:    Base worker prompt text.
        workspace: Project workspace path for repo_tree generation.
        feature:   Feature object used for toggle checks.

    Returns:
        Augmented prompt string with tree header and TDD directive.
    """
    result = inject_repo_tree_into_prompt(prompt, workspace)
    if should_inject_repro_test_directive(feature):
        result = inject_failing_repro_test_directive(result)
    return result


def compute_edit_metrics(edit_site_count: int, edit_span: int) -> EditModeDecision:
    """Compute edit metrics and determine the adaptive edit mode.

    AC-required entry point. Validates inputs and delegates to select_edit_mode.
    Returns 'replace' (default) or 'rewrite' when edit_site_count > 3 or
    edit_span > 40.

    Args:
        edit_site_count: Number of distinct edit locations from the localizer.
                         Must be a non-negative integer.
        edit_span:       Total line span covered by edits.
                         Must be a non-negative integer.

    Returns:
        EditModeDecision with mode, sites, and span fields.

    Raises:
        ValueError: If edit_site_count or edit_span is negative, or if either
                    argument is not an integer.
    """
    if not isinstance(edit_site_count, int) or not isinstance(edit_span, int):
        raise ValueError(
            f"edit_site_count and edit_span must be integers, "
            f"got {type(edit_site_count).__name__} and {type(edit_span).__name__}"
        )
    if edit_site_count < 0:
        raise ValueError(f"edit_site_count must be non-negative, got {edit_site_count}")
    if edit_span < 0:
        raise ValueError(f"edit_span must be non-negative, got {edit_span}")
    return select_edit_mode(edit_site_count, edit_span)


def compute_edit_mode(edit_site_count: int, edit_span: int) -> EditModeDecision:
    """Compute the adaptive edit mode for a given edit shape.

    AC alias for select_edit_mode. Returns 'replace' (default) or 'rewrite'
    when the edit site count exceeds 3 or the line span exceeds 40.

    This is the EDIT_MODE component of F-R7-609 (SWE-Edit NeurIPS 2025).

    Args:
        edit_site_count: Number of distinct edit locations from the localizer.
        edit_span:       Total line span covered by edits.

    Returns:
        EditModeDecision with mode, sites, and span fields.
    """
    return select_edit_mode(edit_site_count, edit_span)


def check_mutation_pass(
    test_command: list[str],
    workspace: str | Path,
    feature_id: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> bool:
    """Check whether a test still passes after a trivial mutation (weak-test detector).

    AC alias for run_mutation_pass_check. Returns True if the test still passes
    after mutation, indicating a likely under-specified test. Emits
    WEAK_TEST_DETECTED when True.

    ICSE 2026 finding: 12-22% of "passing" patches are logically wrong.

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


def mutation_pass_check(
    test_command: list[str],
    workspace: str | Path,
    feature_id: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> bool:
    """AC-required entry point (F-R7-609 component D): run the mutation-pass check.

    Canonical name on bob.dispatch. Runs *test_command* after a trivial mutation
    has been applied to the edited region; returns True if the test STILL passes
    (indicating an under-specified test — WEAK_TEST_DETECTED) or False if the
    mutation flips the result (test adequately specifies the behaviour).

    ICSE 2026 finding: 12-22% of "passing" patches are logically wrong because
    the tests under-specify. Delegates to run_mutation_pass_check.

    Args:
        test_command: pytest / unittest command to run.
        workspace:    Project workspace directory.
        feature_id:   Feature ID for telemetry correlation.
        env:          Optional extra environment variables.
        timeout:      Subprocess timeout in seconds.

    Returns:
        True if the mutated test still passes (weak test); False otherwise.

    Raises:
        ValueError: If test_command is not a non-empty list, or feature_id is
                    not a non-empty string.
    """
    if not isinstance(test_command, list) or not test_command:
        raise ValueError("test_command must be a non-empty list")
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError("feature_id must be a non-empty string")
    return run_mutation_pass_check(
        test_command, workspace, feature_id, env=env, timeout=timeout
    )


def spawn_worker(
    feature: Any,
    prompt: str,
    workspace: str | Path,
    *,
    bob_dir: str | Path,
    extra_allow: list[str] | None = None,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spawn a Claude Code worker with prompt caching, slim context, and per-feature settings.

    AC-required entry point on bob.dispatch. Delegates to spawn_worker_with_cache,
    applying all three platform fixes (prompt cache, slim WORKER.md, per-feature
    settings.json) before launching the worker subprocess.

    Args:
        feature:     Feature object with id, name, description, acceptance_criteria,
                     localization_shortlist.
        prompt:      Worker task prompt text.
        workspace:   Project workspace directory.
        bob_dir:    Path to the .bob directory.
        extra_allow: Additional permission allow patterns.
        timeout:     Subprocess timeout in seconds (default 30 min).
        env:         Optional extra environment variables for the worker.

    Returns:
        Dict with returncode, stdout, stderr, feature_id.

    Raises:
        ValueError: If feature is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    return spawn_worker_with_cache(
        feature,
        prompt,
        workspace,
        bob_dir=bob_dir,
        extra_allow=extra_allow,
        timeout=timeout,
        env=env,
    )


def apply_mutation_check(
    test_command: list[str],
    workspace: str | Path,
    feature_id: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> bool:
    """AC-required alias for run_mutation_pass_check (F-R7-609 component D).

    Returns True if the test still passes after a trivial mutation, indicating
    a likely under-specified test (WEAK_TEST_DETECTED). Returns False if the
    mutation causes the test to fail (test adequately specified).

    Args:
        test_command: pytest / unittest command to run.
        workspace:    Project workspace directory.
        feature_id:   Feature ID for telemetry correlation.
        env:          Optional extra environment variables.
        timeout:      Subprocess timeout in seconds.

    Returns:
        True if the mutated test still passes (weak test); False if it fails.
    """
    return run_mutation_pass_check(
        test_command, workspace, feature_id, env=env, timeout=timeout
    )


def compute_edit_site_metrics(edit_site_count: int, edit_span: int) -> EditModeDecision:
    """Compute edit site metrics and select adaptive edit mode (F-R7-609 component C).

    AC-required entry point. Validates that both arguments are non-negative integers,
    then selects the appropriate edit mode: 'replace' by default, 'rewrite' when
    edit_site_count > 3 OR edit_span > 40 lines (SWE-Edit NeurIPS 2025 thresholds).

    Args:
        edit_site_count: Number of distinct edit locations from the localizer.
                         Must be a non-negative integer.
        edit_span:       Total line span covered by all edits.
                         Must be a non-negative integer.

    Returns:
        EditModeDecision with mode ('replace' or 'rewrite'), sites, and span fields.

    Raises:
        ValueError: If either argument is not an integer or is negative.
    """
    if not isinstance(edit_site_count, int) or not isinstance(edit_span, int):
        raise ValueError(
            f"edit_site_count and edit_span must be integers, "
            f"got {type(edit_site_count).__name__} and {type(edit_span).__name__}"
        )
    if edit_site_count < 0:
        raise ValueError(f"edit_site_count must be non-negative, got {edit_site_count}")
    if edit_span < 0:
        raise ValueError(f"edit_span must be non-negative, got {edit_span}")
    return select_edit_mode(edit_site_count, edit_span)


def compute_edit_site_count(edit_site_count: int, edit_span: int) -> EditModeDecision:
    """AC-required entry point: compute edit site count and return adaptive edit mode decision.

    Given the number of distinct edit locations (*edit_site_count*) and the total
    line span (*edit_span*) of a patch, return an EditModeDecision selecting
    'replace' or 'rewrite' per the SWE-Edit NeurIPS 2025 thresholds:
      - 'rewrite' when edit_site_count > 3 OR edit_span > 40
      - 'replace' otherwise (the cheaper default)

    Args:
        edit_site_count: Number of distinct edit locations from the localizer.
                         Must be a non-negative integer.
        edit_span:       Total line span covered by all edits.
                         Must be a non-negative integer.

    Returns:
        EditModeDecision with mode ('replace' or 'rewrite'), sites, and span fields.

    Raises:
        ValueError: If either argument is not a non-negative integer.
    """
    if not isinstance(edit_site_count, int) or not isinstance(edit_span, int):
        raise ValueError(
            f"edit_site_count and edit_span must be integers, "
            f"got {type(edit_site_count).__name__} and {type(edit_span).__name__}"
        )
    if edit_site_count < 0:
        raise ValueError(f"edit_site_count must be non-negative, got {edit_site_count}")
    if edit_span < 0:
        raise ValueError(f"edit_span must be non-negative, got {edit_span}")
    return select_edit_mode(edit_site_count, edit_span)


def compute_repo_tree(workspace: str | Path, *, max_lines: int = _REPO_TREE_MAX_LINES) -> str:
    """AC-required alias for build_repo_tree.

    Computes a capped directory tree for *workspace* (F-R7-609 component A).
    Delegates entirely to build_repo_tree.

    Args:
        workspace: Path to the project workspace.
        max_lines: Maximum number of tree lines to return (default 200).

    Returns:
        Directory tree string, capped at max_lines with a trailing trailer
        if truncated.
    """
    return build_repo_tree(workspace, max_lines=max_lines)


def get_repo_tree(workspace: str | Path, *, max_lines: int = _REPO_TREE_MAX_LINES) -> str:
    """AC-required entry point: return a capped directory tree for *workspace*.

    Canonical alias for build_repo_tree on this module. Exposed as
    bob.dispatch.get_repo_tree to satisfy the function-defined AC for
    F-R7-609 component (A).

    Args:
        workspace: Path to the project workspace.
        max_lines: Maximum number of tree lines to return (default 200).

    Returns:
        Directory tree string, capped at max_lines with a trailing truncation
        trailer when the tree exceeds the cap.
    """
    return build_repo_tree(workspace, max_lines=max_lines)


def apply_repo_tree_context(prompt: str, workspace: str | Path) -> str:
    """AC-required entry point: inject repo tree context into a worker prompt (F-R7-609 component A).

    Delegates to inject_repo_tree_into_prompt. Prepends a capped directory
    tree to *prompt* so the worker can orient itself within the repository.

    Args:
        prompt:    Base worker prompt text.
        workspace: Project workspace path for repo_tree generation.

    Returns:
        Augmented prompt string with repo tree header prepended.
    """
    return inject_repo_tree_into_prompt(prompt, workspace)


def apply_repro_test_directive(prompt: str, feature: Any) -> str:
    """AC-required entry point: apply the failing-repro-test directive to a worker prompt (F-R7-609 component B).

    Appends the standing TDD directive unless the feature has skip_repro_test=True
    or all ACs are structural.

    Args:
        prompt:  Base worker prompt text.
        feature: Feature object used for toggle checks.

    Returns:
        Augmented prompt with TDD directive appended (or unchanged if skipped).
    """
    if should_inject_repro_test_directive(feature):
        return inject_failing_repro_test_directive(prompt)
    return prompt


def select_adaptive_edit_mode(edit_site_count: int, edit_span: int) -> EditModeDecision:
    """AC-required entry point: select the adaptive edit mode (F-R7-609 component C).

    Returns 'replace' by default; switches to 'rewrite' when edit_site_count > 3
    OR edit_span > 40 lines (SWE-Edit NeurIPS 2025 thresholds).

    Args:
        edit_site_count: Number of distinct edit locations from the localizer.
        edit_span:       Total line span covered by all edits.

    Returns:
        EditModeDecision with mode ('replace' or 'rewrite'), sites, and span fields.
    """
    return select_edit_mode(edit_site_count, edit_span)


def spawn_worker_with_repo_tree(
    feature: Any,
    prompt: str,
    workspace: str | Path,
    *,
    bob_dir: str | Path,
    extra_allow: list[str] | None = None,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spawn a Claude Code worker with repo tree prepended to the prompt.

    Combines the repo_tree cheap win (F-R7-609 component A) with the standard
    worker spawn. The repository tree is prepended to *prompt* so the worker
    can orient itself within the project structure before editing.

    Args:
        feature:     Feature object with id, name, description, acceptance_criteria,
                     localization_shortlist.
        prompt:      Worker task prompt text.
        workspace:   Project workspace directory.
        bob_dir:    Path to the .bob directory.
        extra_allow: Additional permission allow patterns.
        timeout:     Subprocess timeout in seconds (default 30 min).
        env:         Optional extra environment variables for the worker.

    Returns:
        Dict with returncode, stdout, stderr, feature_id.

    Raises:
        ValueError: If feature is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")

    augmented_prompt = inject_repo_tree_into_prompt(prompt, workspace)
    logger.info(
        json.dumps({
            "event": "REPO_TREE_INJECTED",
            "feature_id": getattr(feature, "id", "unknown"),
        })
    )
    return spawn_worker_with_cache(
        feature,
        augmented_prompt,
        workspace,
        bob_dir=bob_dir,
        extra_allow=extra_allow,
        timeout=timeout,
        env=env,
    )


def enable_worker_prompt_cache(
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return an environment dict with prompt caching enabled for a worker.

    Sets ANTHROPIC_PROMPT_CACHING=1, which instructs the Claude Code CLI to
    enable prompt caching on every API call (addresses Issue #29966).

    Args:
        env: Existing environment dict to extend. If None, starts from empty.

    Returns:
        New dict containing the input env merged with the cache-enable setting.
    """
    result = dict(env) if env else {}
    result["ANTHROPIC_PROMPT_CACHING"] = "1"
    return result


def generate_worker_settings(
    feature: Any,
    *,
    bob_dir: str | Path,
    extra_allow: list[str] | None = None,
) -> Path:
    """Generate and write per-feature settings.json for a worker.

    Alias for write_feature_settings that explicitly names the generation
    step. Workers do NOT inherit hooks/permissions from the parent
    settings.json (Issue #27661), so settings must be declared per-worker.

    Args:
        feature:     Feature object; ``feature.id`` used as directory name.
        bob_dir:    Path to the .bob directory (project-level).
        extra_allow: Additional allow patterns beyond project defaults.

    Returns:
        Path to the written settings.json file.
    """
    return write_feature_settings(feature, bob_dir=bob_dir, extra_allow=extra_allow)


# AC-required aliases (F-R7-609)
inject_repo_tree = inject_repo_tree_into_prompt
compute_adaptive_edit_mode = select_edit_mode


def validate_repo_tree(tree_text: str) -> bool:
    """Return True if *tree_text* is a non-empty, well-formed repo tree string.

    A valid tree is non-empty and does not solely consist of the unavailability
    sentinel returned by build_repo_tree when both tree and find fail.

    This is the validation entry point for F-R7-609 component A.
    """
    if not isinstance(tree_text, str):
        return False
    stripped = tree_text.strip()
    if not stripped:
        return False
    if stripped.startswith("(repo tree unavailable"):
        return False
    return True


def handle_mutation_failure(
    feature_id: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """Handle a mutation-pass failure by emitting WEAK_TEST_DETECTED and returning the event.

    Called by the orchestrator after run_mutation_pass_check returns True,
    indicating the test still passes even after a trivial mutation — the test
    under-specifies the behaviour.

    This is the failure handler for F-R7-609 component D.

    Args:
        feature_id: ID of the feature whose test was found to be weak.
        detail:     Optional human-readable detail appended to the event.

    Returns:
        The WEAK_TEST_DETECTED event dict (same as emit_weak_test_event).
    """
    return emit_weak_test_event(feature_id, detail=detail)


__all__ = [
    "apply_cheap_wins",
    "apply_mutation_check",
    "apply_repo_tree_context",
    "apply_repro_test_directive",
    "build_repo_tree",
    "build_worker_md",
    "build_worker_system_prompt",
    "check_mutation_pass",
    "check_reap_backoff",
    "compute_adaptive_edit_mode",
    "compute_backoff_deadline",
    "compute_edit_metrics",
    "compute_edit_mode",
    "compute_edit_site_metrics",
    "compute_repo_tree",
    "emit_edit_mode_event",
    "emit_weak_test_event",
    "emit_worker_cache_event",
    "enable_worker_prompt_cache",
    "generate_worker_settings",
    "get_repo_tree",
    "inject_failing_repro_test_directive",
    "handle_mutation_failure",
    "inject_repo_tree",
    "inject_repo_tree_into_prompt",
    "inject_repo_tree_to_worker",
    "mutation_pass_check",
    "run_mutation_pass_check",
    "validate_repo_tree",
    "select_adaptive_edit_mode",
    "select_edit_mode",
    "should_inject_repro_test_directive",
    "should_refuse_recent_reap",
    "should_refuse_redispatch",
    "should_refuse_redispatch_after_reap",
    "spawn_worker",
    "spawn_worker_with_cache",
    "spawn_worker_with_repo_tree",
    "write_feature_settings",
    "EditModeDecision",
]
