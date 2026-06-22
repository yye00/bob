"""Brownfield scope correction — vendor RepoMapper, reduce BF-5/BF-6 to enforcement.

Post-research scope reductions for BF-1, BF-5, and BF-6:

  (A) BF-1 → vendor RepoMapper as MCP server
      survey.py is now a thin MCP client (~200 LoC) rather than a custom
      tree-sitter + PageRank reimplementation (~2K LoC).
      survey.db is a CACHE of RepoMapper output, not a custom schema.

  (B) BF-5 → just the GitHub-graveyard signal (Signal-A)
      Signal-B (export_without_impl) and Signal-C (todo_cluster) duplicate
      Claude Code session-resume + Plan Mode. They are gated behind
      feature.deep_resurrection_scan defaulting OFF.

  (C) BF-6 → AskUserQuestion enforcement (interactive) + BRANCH (headless)
      The custom Pydantic + k-sample classifier is only active in headless
      mode. Interactive mode delegates to AskUserQuestion via the host SDK.

  (D) src/bob3/CLAUDE.md contains only meta-loop guidance; operator memory
      bullets are moved to per-feature WORKER.md files.

Why permanent_forward_carry: scope discipline.  Without this, every future
generation pays the cost of three duplicative features.
"""

from __future__ import annotations

from typing import Any


def brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf() -> dict[str, Any]:
    """Return a scope-correction summary for BF-1, BF-5, and BF-6.

    Each entry in scope_reductions describes one scope-reduction decision:
      id          — feature ID (BF-1, BF-5, BF-6)
      original    — what was originally planned
      reduction   — what the correction reduces it to
      rationale   — why Claude Code already covers the removed parts
      status      — enforcement layer applied

    Returns:
        dict with keys:
          scope_reductions  — list of reduction dicts (one per BF)
          enforcement_files — source files that apply the enforcement
          permanent_forward_carry — True (this decision propagates to future gens)
    """
    scope_reductions: list[dict[str, Any]] = [
        {
            "id": "BF-1",
            "feature": "Brownfield prerequisite — queryable map of an existing repo",
            "original": (
                "Custom tree-sitter + PageRank implementation (~2K LoC) "
                "in src/bob3/brownfield/survey.py"
            ),
            "reduction": (
                "Thin stdio MCP launcher for Aider's RepoMapper server (~200 LoC). "
                "survey.db is a CACHE of RepoMapper output, not a custom reimplementation."
            ),
            "rationale": (
                "RepoMapper ships symbol-graph + PageRank as an MCP server. "
                "Bob3 is a thin MCP client; no need to reimplement the computation."
            ),
            "enforcement_file": "src/bob3/brownfield/survey.py",
            "enforcement_function": "launch_repomapper_mcp",
            "status": "applied",
        },
        {
            "id": "BF-5",
            "feature": "Resurrection detector — Tier-1 partial-work detector",
            "original": (
                "Three Tier-1 signals: Signal-A (stale PR/branch), "
                "Signal-B (export-without-impl), Signal-C (TODO clusters)"
            ),
            "reduction": (
                "Keep ONLY Signal-A (graveyard PRs) default-ON. "
                "Signal-B and Signal-C gated behind "
                "feature.deep_resurrection_scan=True (defaults OFF)."
            ),
            "rationale": (
                "Signal-B (export-without-impl) and Signal-C (TODO clusters) "
                "are surfaced by Claude Code session-resume + Plan Mode. "
                "Only the GitHub-graveyard signal is unique to bob3."
            ),
            "enforcement_file": "src/bob3/brownfield/resurrection.py",
            "enforcement_function": "filter_signals_by_feature_flags",
            "status": "applied",
        },
        {
            "id": "BF-6",
            "feature": "Elicitation classifier + clarification-budget gate",
            "original": (
                "Custom Pydantic + k-sample classifier for all elicitation paths "
                "(interactive and headless)"
            ),
            "reduction": (
                "Interactive path: emit AskUserQuestion via host SDK (no Pydantic reimplementation). "
                "Headless path: BRANCH-INTO-CANDIDATES (F-R7-605 path) — "
                "this is the only bob3-specific logic."
            ),
            "rationale": (
                "Claude Code's AskUserQuestion + Plan Mode already covers interactive elicitation. "
                "Only the headless path (claude -p, no human) needs bob3-specific branching."
            ),
            "enforcement_file": "src/bob3/brownfield/elicit.py",
            "enforcement_function": "branch_on_mode",
            "status": "applied",
        },
    ]

    enforcement_files = [r["enforcement_file"] for r in scope_reductions]

    return {
        "scope_reductions": scope_reductions,
        "enforcement_files": enforcement_files,
        "permanent_forward_carry": True,
        "claude_md_status": (
            "src/bob3/CLAUDE.md contains meta-loop guidance only; "
            "operator memory bullets demoted to per-feature WORKER.md files."
        ),
    }
