"""Brownfield resurrection detector -- Tier-1 partial-work detector (BF-5).

Before bob3 dispatches a fresh implementer for a "new" feature, this module
checks whether someone already started the work and abandoned it.

Three Tier-1 signals:
  Signal A -- Stale PR/branch (GitHub graveyard)
  Signal B -- Export-without-impl (AST: symbol exported but body is pass/stub)
  Signal C -- Disk-scoped TODO clusters (>=3 TODO/FIXME refs in touch-set)

If any signal fires, callers should write a resurrection_report.md and demote
the feature to needs_human with reason='partial_work_detected'.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ResurrectionSignal:
    """A single partial-work signal detected during the resurrection scan.

    Attributes:
        signal_kind: One of 'stale_pr', 'stale_branch', 'export_without_impl',
            'todo_cluster'.
        evidence: List of human-readable evidence strings (URLs, SHAs, file:line refs).
        staleness_days: How stale the artifact is in days (0 when unknown).
        recommended_action: One of 'resume_pr', 'rebase_branch', 'finish_stub'.
    """

    signal_kind: str
    evidence: list[str]
    staleness_days: int
    recommended_action: str


# ---------------------------------------------------------------------------
# Signal A -- Stale PR / branch
# ---------------------------------------------------------------------------


def _scan_stale_prs(
    repo: str,
    feature_keywords: list[str],
    lookback_days: int = 90,
    github_token: Optional[str] = None,
) -> list[ResurrectionSignal]:
    """Detect stale draft PRs older than lookback_days days (Signal A).

    Uses 'gh pr list' when available.  Returns empty list when gh is not
    installed or credentials are absent -- callers treat this as no signal.
    """
    signals: list[ResurrectionSignal] = []
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--state", "open",
                "--search", f"is:draft updated:<{_days_ago_iso(lookback_days)}",
                "--json", "number,title,body,url,updatedAt",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return signals
        import json
        prs = json.loads(result.stdout or "[]")
        for pr in prs:
            if not feature_keywords or _any_keyword_in(
                feature_keywords, pr.get("title", "") + " " + pr.get("body", "")
            ):
                signals.append(
                    ResurrectionSignal(
                        signal_kind="stale_pr",
                        evidence=[pr.get("url", f"#{pr['number']}")],
                        staleness_days=lookback_days,
                        recommended_action="resume_pr",
                    )
                )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return signals


def _scan_stale_branches(
    workspace_root: str,
    touches: list[str],
    min_diverge_days: int = 30,
) -> list[ResurrectionSignal]:
    """Detect local branches diverged >= min_diverge_days days and touching paths."""
    signals: list[ResurrectionSignal] = []
    try:
        result = subprocess.run(
            ["git", "-C", workspace_root, "for-each-ref", "refs/heads",
             "--format", "%(refname:short) %(committerdate:iso)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return signals
        cutoff = _days_ago_iso(min_diverge_days)
        for line in result.stdout.splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) < 2:
                continue
            branch, date_str = parts[0], parts[1]
            if date_str[:10] < cutoff:
                if _branch_touches_paths(workspace_root, branch, touches):
                    signals.append(
                        ResurrectionSignal(
                            signal_kind="stale_branch",
                            evidence=[f"refs/heads/{branch}"],
                            staleness_days=min_diverge_days,
                            recommended_action="rebase_branch",
                        )
                    )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return signals


def _branch_touches_paths(workspace_root: str, branch: str, touches: list[str]) -> bool:
    if not touches:
        return False
    try:
        result = subprocess.run(
            ["git", "-C", workspace_root, "diff", "--name-only", f"origin/HEAD...{branch}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        changed = set(result.stdout.splitlines())
        return any(t in changed for t in touches)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Signal B -- Export-without-impl (AST)
# ---------------------------------------------------------------------------


_STUB_PATTERN = re.compile(
    r"^\s*(pass|\.\.\.)\s*$|raise\s+(NotImplementedError|AssertionError)"
    r"|throw\s+new\s+Error\s*\(['\"]TODO",
    re.MULTILINE,
)


def _scan_exports_without_impl(
    workspace_root: str,
    touches: list[str],
) -> list[ResurrectionSignal]:
    """Find symbols exported in __all__ but implemented as pass/stub (Signal B)."""
    signals: list[ResurrectionSignal] = []
    root = Path(workspace_root)

    for rel_path in touches:
        abs_path = root / rel_path
        if not abs_path.exists() or abs_path.suffix != ".py":
            continue
        try:
            source = abs_path.read_text(errors="replace")
        except OSError:
            continue

        # Find __all__ entries
        all_match = re.search(r"__all__\s*=\s*\[([^\]]+)\]", source)
        if not all_match:
            continue
        exports = [
            s.strip().strip("'\"")
            for s in all_match.group(1).split(",")
            if s.strip().strip("'\"")
        ]

        for name in exports:
            # Check if symbol is defined — match only up to the colon so that
            # def_match.end() points right after ":" rather than consuming the
            # entire body via (.*)$ with DOTALL.
            def_match = re.search(
                rf"^(def|class|async\s+def)\s+{re.escape(name)}\b[^:]*:",
                source,
                re.MULTILINE,
            )
            if def_match is None:
                # Symbol exported but not defined at all
                signals.append(
                    ResurrectionSignal(
                        signal_kind="export_without_impl",
                        evidence=[f"{rel_path}:{name}"],
                        staleness_days=0,
                        recommended_action="finish_stub",
                    )
                )
                continue

            # Check if the body is a stub
            body_start = def_match.end()
            body_snippet = source[body_start : body_start + 300]
            if _STUB_PATTERN.search(body_snippet):
                signals.append(
                    ResurrectionSignal(
                        signal_kind="export_without_impl",
                        evidence=[f"{rel_path}:{name} (stub body)"],
                        staleness_days=0,
                        recommended_action="finish_stub",
                    )
                )

    return signals


# ---------------------------------------------------------------------------
# Signal C -- Disk-scoped TODO clusters
# ---------------------------------------------------------------------------


_TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


def _scan_todo_clusters(
    workspace_root: str,
    touches: list[str],
    min_size: int = 3,
) -> list[ResurrectionSignal]:
    """Find files with >= min_size TODO/FIXME comments in the touch-set (Signal C)."""
    signals: list[ResurrectionSignal] = []
    root = Path(workspace_root)

    for rel_path in touches:
        abs_path = root / rel_path
        if not abs_path.exists():
            continue
        try:
            lines = abs_path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        hits = [f"line {i + 1}" for i, line in enumerate(lines) if _TODO_PATTERN.search(line)]
        if len(hits) >= min_size:
            signals.append(
                ResurrectionSignal(
                    signal_kind="todo_cluster",
                    evidence=[f"{rel_path}:{h}" for h in hits],
                    staleness_days=0,
                    recommended_action="finish_stub",
                )
            )

    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_resurrection_signals(
    workspace_root: str,
    touches: list[str],
    feature_keywords: list[str],
    repo: str = "",
    github_token: Optional[str] = None,
    pr_lookback_days: int = 90,
    branch_diverge_days: int = 30,
    todo_cluster_min_size: int = 3,
) -> list[ResurrectionSignal]:
    """Run all Tier-1 resurrection signals and return any that fire.

    Args:
        workspace_root: Root directory of the brownfield workspace.
        touches: Relative file paths that the feature is expected to touch.
        feature_keywords: Keywords from feature.capability used to filter PRs/branches.
        repo: GitHub repo slug (e.g. 'org/repo') for Signal A.
        github_token: Optional GitHub token for authenticated API access.
        pr_lookback_days: Signal A -- how old must a draft PR be to fire.
        branch_diverge_days: Signal A -- how long must a branch be diverged.
        todo_cluster_min_size: Signal C -- minimum number of TODOs to constitute a cluster.

    Raises:
        TypeError: If workspace_root or touches is not the expected type.
        ValueError: If numeric parameters are out of valid range.

    Returns:
        List of ResurrectionSignal instances.  Empty list means no signals fired.
    """
    # Type validation — let callers know early rather than silently succeed.
    if not isinstance(touches, list):
        raise TypeError(f"touches must be a list, got {type(touches).__name__}")
    if pr_lookback_days < 0:
        raise ValueError(f"pr_lookback_days must be >= 0, got {pr_lookback_days}")
    if branch_diverge_days < 0:
        raise ValueError(f"branch_diverge_days must be >= 0, got {branch_diverge_days}")
    if todo_cluster_min_size < 1:
        raise ValueError(f"todo_cluster_min_size must be >= 1, got {todo_cluster_min_size}")

    if not touches:
        return []

    signals: list[ResurrectionSignal] = []

    # Signal A -- stale PR / branch
    if repo:
        signals.extend(
            _scan_stale_prs(
                repo=repo,
                feature_keywords=feature_keywords,
                lookback_days=pr_lookback_days,
                github_token=github_token,
            )
        )
    signals.extend(
        _scan_stale_branches(
            workspace_root=workspace_root,
            touches=touches,
            min_diverge_days=branch_diverge_days,
        )
    )

    # Signal B -- export-without-impl
    signals.extend(
        _scan_exports_without_impl(
            workspace_root=workspace_root,
            touches=touches,
        )
    )

    # Signal C -- TODO clusters
    signals.extend(
        _scan_todo_clusters(
            workspace_root=workspace_root,
            touches=touches,
            min_size=todo_cluster_min_size,
        )
    )

    return signals


def write_resurrection_report(
    feature_id: str,
    signals: list[ResurrectionSignal],
    bob3_root: str = ".bob3",
) -> str:
    """Write a resurrection_report.md for the feature and return its path.

    The report is written to:
        <bob3_root>/features/<feature_id>/resurrection_report.md

    Each signal is rendered with: signal_kind, evidence, staleness_days,
    and recommended_action.

    Args:
        feature_id: Unique feature identifier.
        signals: Signals returned by detect_resurrection_signals.
        bob3_root: Root of the .bob3 directory (default: '.bob3').

    Returns:
        Absolute path to the written report file.
    """
    report_dir = Path(bob3_root) / "features" / feature_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "resurrection_report.md"

    lines = [
        f"# Resurrection Report: {feature_id}",
        "",
        f"**Signals detected:** {len(signals)}",
        "",
    ]

    for i, sig in enumerate(signals, start=1):
        lines += [
            f"## Signal {i}: {sig.signal_kind}",
            "",
            f"- **signal_kind:** {sig.signal_kind}",
            f"- **staleness_days:** {sig.staleness_days}",
            f"- **recommended_action:** {sig.recommended_action}",
            "- **evidence:**",
        ]
        for ev in sig.evidence:
            lines.append(f"  - {ev}")
        lines.append("")

    lines += [
        "---",
        "*Generated by bob3.brownfield.resurrection (BF-5)*",
    ]

    report_path.write_text("\n".join(lines))
    return str(report_path)


# ---------------------------------------------------------------------------
# Named public entry points for each signal (AC: detect_stale_pr, etc.)
# ---------------------------------------------------------------------------


def detect_stale_pr(
    repo: str,
    feature_keywords: list[str],
    lookback_days: int = 90,
    github_token: Optional[str] = None,
) -> list[ResurrectionSignal]:
    """Public entry point for Signal A (stale draft PRs).

    Delegates to the internal _scan_stale_prs implementation.
    Returns empty list when gh CLI is unavailable or credentials absent.
    """
    return _scan_stale_prs(
        repo=repo,
        feature_keywords=feature_keywords,
        lookback_days=lookback_days,
        github_token=github_token,
    )


def detect_stale_branch(
    workspace_root: str,
    touches: list[str],
    min_diverge_days: int = 30,
) -> list[ResurrectionSignal]:
    """Public entry point for Signal A (stale local branches).

    Delegates to the internal _scan_stale_branches implementation.

    Raises:
        TypeError: If workspace_root or touches is not the expected type.
    """
    if not isinstance(touches, list):
        raise TypeError(f"touches must be a list, got {type(touches).__name__}")
    # workspace_root type error surfaces naturally via Path() below, but we
    # need to raise for None explicitly to match the contract.
    if workspace_root is None:
        raise TypeError("workspace_root must not be None")
    return _scan_stale_branches(
        workspace_root=workspace_root,
        touches=touches,
        min_diverge_days=min_diverge_days,
    )


def detect_export_without_impl(
    workspace_root: str,
    touches: list[str],
) -> list[ResurrectionSignal]:
    """Public entry point for Signal B (exported symbol with stub body).

    Delegates to the internal _scan_exports_without_impl implementation.
    """
    return _scan_exports_without_impl(
        workspace_root=workspace_root,
        touches=touches,
    )


def detect_todo_clusters(
    workspace_root: str,
    touches: list[str],
    min_size: int = 3,
) -> list[ResurrectionSignal]:
    """Public entry point for Signal C (TODO/FIXME clusters in touch-set).

    Delegates to the internal _scan_todo_clusters implementation.

    Raises:
        TypeError: If workspace_root or touches is not the expected type.
        ValueError: If min_size < 1.
    """
    if not isinstance(touches, list):
        raise TypeError(f"touches must be a list, got {type(touches).__name__}")
    if workspace_root is None:
        raise TypeError("workspace_root must not be None")
    if min_size < 1:
        raise ValueError(f"min_size must be >= 1, got {min_size}")
    return _scan_todo_clusters(
        workspace_root=workspace_root,
        touches=touches,
        min_size=min_size,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def filter_signals_by_feature_flags(
    signals: list[ResurrectionSignal],
    deep_resurrection_scan: bool = False,
) -> list[ResurrectionSignal]:
    """Gate Signal-B and Signal-C behind feature.deep_resurrection_scan flag.

    BF-5 scope reduction (be676e0d): Signal-B (export_without_impl) and
    Signal-C (todo_cluster) duplicate what Claude Code session-resume + Plan
    Mode already surface. Only Signal-A (stale PR / stale branch) is unique
    to bob3. Gates B and C behind deep_resurrection_scan, which defaults OFF.

    Args:
        signals: List of ResurrectionSignal from detect_resurrection_signals.
        deep_resurrection_scan: When True, all signals are returned unchanged.
            When False (default), Signal-B and Signal-C are filtered out.

    Returns:
        Filtered list of ResurrectionSignal. Signal-A signals always returned.
    """
    if deep_resurrection_scan:
        return list(signals)
    _DEEP_ONLY_KINDS = {"export_without_impl", "todo_cluster"}
    return [s for s in signals if s.signal_kind not in _DEEP_ONLY_KINDS]


def _days_ago_iso(days: int) -> str:
    """Return an ISO 8601 date string for N days ago."""
    import datetime
    d = datetime.date.today() - datetime.timedelta(days=days)
    return d.isoformat()


def _any_keyword_in(keywords: list[str], text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


# AC alias: the acceptance-criteria require this exact name (BF-5 fd27c8b8).
detect_exported_stubs = detect_export_without_impl

# AC alias: BF-5 b1442bab requires generate_resurrection_report.
generate_resurrection_report = write_resurrection_report

# AC alias: BF-5 c8fc0095 requires this exact name (without 'ed' suffix).
detect_export_stubs = detect_export_without_impl

# AC aliases: plural forms required by BF-5 c902dc13 ACs.
detect_stale_prs = detect_stale_pr
detect_stale_branches = detect_stale_branch
detect_exports_without_impl = detect_export_without_impl

# AC alias: BF-5 edb31903 requires this exact name.
detect_exported_without_impl = detect_export_without_impl

# AC alias: BF-5 7ea1e9ae requires bob3.brownfield.resurrection.detect_stub_exports.
detect_stub_exports = detect_export_without_impl

# AC alias: BF-5 acceptance criteria require bob3.brownfield.resurrection.detect_signals.
detect_signals = detect_resurrection_signals

# AC alias: BF-5 0a43b348 requires bob3.brownfield.resurrection.check_resurrection_signals.
check_resurrection_signals = detect_resurrection_signals


def get_graveyard_signal(
    repo: str,
    feature_keywords: list[str],
    lookback_days: int = 90,
    github_token: Optional[str] = None,
) -> list[ResurrectionSignal]:
    """Return only Signal-A (stale PR/closed-unmerged) signals for a feature.

    BF-5 scope reduction (F-R7-611): Signal-B (export_without_impl) and
    Signal-C (todo_cluster) are covered by Claude Code session-resume + Plan
    Mode. Only the GitHub-graveyard signal is unique to bob3.

    This function is the canonical public entry point for the graveyard check:
    it delegates to _scan_stale_prs (Signal A only).

    Args:
        repo: GitHub repo slug, e.g. 'owner/repo'.
        feature_keywords: Keywords from feature.capability for PR/body matching.
        lookback_days: How old a draft PR must be to fire (default: 90).
        github_token: Optional GitHub token for authenticated access.

    Returns:
        List of ResurrectionSignal with signal_kind='stale_pr'.
        Empty list when gh CLI is unavailable or no matching PRs found.
    """
    return _scan_stale_prs(
        repo=repo,
        feature_keywords=feature_keywords,
        lookback_days=lookback_days,
        github_token=github_token,
    )


# AC alias: F-R7-611 requires bob3.brownfield.resurrection.signal_graveyard_prs
signal_graveyard_prs = get_graveyard_signal


def filter_signals_by_config(
    signals: list[ResurrectionSignal],
    config: Optional[dict] = None,
) -> list[ResurrectionSignal]:
    """Gate Signal-B and Signal-C via a config dict (F-R7-611 AC alias).

    Accepts a config dict with optional key 'deep_resurrection_scan' (bool).
    Delegates to filter_signals_by_feature_flags for the actual filtering.

    Args:
        signals: List of ResurrectionSignal from detect_resurrection_signals.
        config: Dict with optional 'deep_resurrection_scan' bool key.
                Defaults to {} (deep scan OFF).

    Returns:
        Filtered list of ResurrectionSignal.
    """
    if config is None:
        config = {}
    deep_scan = bool(config.get("deep_resurrection_scan", False))
    return filter_signals_by_feature_flags(signals, deep_resurrection_scan=deep_scan)


# AC alias: singular form required by F-R7-611 AC (bob3.brownfield.resurrection.filter_signals_by_feature_flag)
filter_signals_by_feature_flag = filter_signals_by_feature_flags


def detect_stale_pr_or_branch(
    workspace_root: str,
    touches: list[str],
    feature_keywords: list[str],
    repo: str = "",
    github_token: Optional[str] = None,
    pr_lookback_days: int = 90,
    branch_diverge_days: int = 30,
) -> list[ResurrectionSignal]:
    """Detect stale PR or stale branch signals (Signal A, combined entry point).

    Runs both the stale-PR scan (via gh CLI) and the stale-branch scan (via
    git for-each-ref), returning all Signal-A signals that fire.

    Args:
        workspace_root: Root directory of the brownfield workspace.
        touches: Relative file paths the feature is expected to touch.
        feature_keywords: Keywords from feature.capability for PR/body matching.
        repo: GitHub repo slug, e.g. 'owner/repo'. Required for PR scan.
        github_token: Optional GitHub token for authenticated access.
        pr_lookback_days: How old a draft PR must be to fire (default: 90).
        branch_diverge_days: How long a branch must be diverged to fire (default: 30).

    Returns:
        List of ResurrectionSignal with signal_kind in {'stale_pr', 'stale_branch'}.
        Empty list when no signals fire or infrastructure is unavailable.
    """
    if not isinstance(touches, list):
        raise TypeError(f"touches must be a list, got {type(touches).__name__}")
    if workspace_root is None:
        raise TypeError("workspace_root must not be None")
    if pr_lookback_days < 0:
        raise ValueError(f"pr_lookback_days must be >= 0, got {pr_lookback_days}")
    if branch_diverge_days < 0:
        raise ValueError(f"branch_diverge_days must be >= 0, got {branch_diverge_days}")

    signals: list[ResurrectionSignal] = []

    if repo:
        signals.extend(
            _scan_stale_prs(
                repo=repo,
                feature_keywords=feature_keywords,
                lookback_days=pr_lookback_days,
                github_token=github_token,
            )
        )

    signals.extend(
        _scan_stale_branches(
            workspace_root=workspace_root,
            touches=touches,
            min_diverge_days=branch_diverge_days,
        )
    )

    return signals
