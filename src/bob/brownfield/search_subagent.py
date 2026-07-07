"""WarpGrep search sub-agent pattern for brownfield localization (Feature 5c5826d3).

Implements the Search-subagent pattern (WarpGrep v2):
- Spawns a dedicated 'locator' sub-agent whose entire job is grep → return candidates
- The transcript is discarded after the sub-agent returns (doesn't pollute parent context)
- Bypasses the localizer (F-R7-600) when it returns >20 candidate symbols
- Output schema: list[{path, start_line, end_line, confidence, rationale_snippet}]

The search sub-agent is a pure function: given a feature intent and workspace path,
it returns 3-5 candidate code spans with confidence scores.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Maximum candidate symbols from the localizer before we bypass it and use
# the search sub-agent instead.
LOCALIZER_OVERFLOW_THRESHOLD = 20

# Number of candidates to return from the search sub-agent.
MAX_CANDIDATES = 5
MIN_CANDIDATES = 3


@dataclass
class SearchResult:
    """A single candidate code span returned by the search sub-agent.

    Attributes:
        path: Relative path to the source file.
        start_line: 1-based line number where the span begins.
        end_line: 1-based line number where the span ends (inclusive).
        confidence: Float in [0.0, 1.0] representing match confidence.
        rationale_snippet: Short explanation of why this span was chosen.
    """

    path: str
    start_line: int
    end_line: int
    confidence: float
    rationale_snippet: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict matching the output schema."""
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "confidence": self.confidence,
            "rationale_snippet": self.rationale_snippet,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SearchResult":
        """Construct a SearchResult from a dict (e.g. from JSON output)."""
        return cls(
            path=str(d["path"]),
            start_line=int(d["start_line"]),
            end_line=int(d["end_line"]),
            confidence=float(d.get("confidence", 0.5)),
            rationale_snippet=str(d.get("rationale_snippet", "")),
        )


# ---------------------------------------------------------------------------
# Grep-based candidate extraction (the actual locator logic)
# ---------------------------------------------------------------------------


def _grep_candidates(
    keywords: list[str],
    workspace: Path,
    *,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Run ripgrep/grep against the workspace and return raw match dicts.

    Returns list of {path, line_number, text} for each match.
    Uses ripgrep if available, falls back to grep.
    """
    if not keywords:
        return []

    pattern = "|".join(re.escape(kw) for kw in keywords)

    # Try ripgrep first (faster, respects .gitignore)
    try:
        result = subprocess.run(
            ["rg", "--json", "--max-count", str(max_results), "-e", pattern, str(workspace)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode in (0, 1):
            matches = []
            for line in result.stdout.splitlines():
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "match":
                        data = obj["data"]
                        matches.append({
                            "path": data["path"]["text"],
                            "line_number": data["line_number"],
                            "text": data["lines"]["text"].rstrip(),
                        })
                except (json.JSONDecodeError, KeyError):
                    continue
            return matches
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: plain grep
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", "-E", pattern, str(workspace)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        matches = []
        for line in result.stdout.splitlines()[:max_results]:
            # Format: path:lineno:text
            parts = line.split(":", 2)
            if len(parts) >= 3:
                try:
                    matches.append({
                        "path": parts[0],
                        "line_number": int(parts[1]),
                        "text": parts[2].strip(),
                    })
                except ValueError:
                    continue
        return matches
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _score_match(
    match: dict[str, Any],
    intent: dict[str, Any],
    keywords: list[str],
) -> float:
    """Score a grep match against the intent to produce a confidence value."""
    text = match.get("text", "").lower()
    path = match.get("path", "").lower()

    score = 0.0

    # Keyword frequency in match line
    for kw in keywords:
        if kw.lower() in text:
            score += 0.3
        if kw.lower() in path:
            score += 0.1

    # Boost for function/class definitions
    if re.search(r"^\s*(def|class)\s+", text):
        score += 0.2

    # Boost for target subsystem in path
    target = intent.get("target_subsystem", "").lower()
    if target and target in path:
        score += 0.2

    # Boost for capability keywords in the line
    capability = intent.get("capability", "").lower()
    if capability:
        cap_tokens = re.findall(r"[a-z0-9]+", capability)
        for tok in cap_tokens:
            if len(tok) > 3 and tok in text:
                score += 0.1

    return min(1.0, score)


def _group_matches_into_spans(
    matches: list[dict[str, Any]],
    intent: dict[str, Any],
    keywords: list[str],
    *,
    context_lines: int = 10,
    max_candidates: int = MAX_CANDIDATES,
) -> list[SearchResult]:
    """Convert raw grep matches into SearchResult spans, deduplicated and ranked."""
    if not matches:
        return []

    # Score each match
    scored = [
        (match, _score_match(match, intent, keywords))
        for match in matches
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Group nearby matches in the same file into spans; pick top candidates
    results: list[SearchResult] = []
    seen_spans: set[tuple[str, int, int]] = set()

    for match, confidence in scored:
        if len(results) >= max_candidates:
            break
        if confidence < 0.1:
            continue

        path = match["path"]
        lineno = match["line_number"]

        # Expand span by context_lines
        start_line = max(1, lineno - context_lines // 2)
        end_line = lineno + context_lines // 2

        # Deduplicate overlapping spans in the same file
        span_key = (path, start_line // (context_lines + 1), 0)
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)

        results.append(SearchResult(
            path=path,
            start_line=start_line,
            end_line=end_line,
            confidence=round(confidence, 3),
            rationale_snippet=match.get("text", "")[:120],
        ))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def spawn_search_subagent(
    intent: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    keywords: Optional[list[str]] = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[SearchResult]:
    """Spawn a search sub-agent to locate candidate code spans for a feature.

    This function implements the WarpGrep v2 search sub-agent pattern:
    1. Extract keywords from the intent (or use provided keywords).
    2. Run grep over the workspace to find raw matches.
    3. Score and group matches into candidate spans.
    4. Return up to max_candidates SearchResult objects.

    The "sub-agent" here is the grep process itself — its output (raw match
    data) is transient and not stored in the parent's context beyond the
    returned SearchResult list.

    Args:
        intent: Feature intent dict with 'capability', 'target_subsystem',
                and 'keywords' fields (same schema as localizer).
        workspace: Path to the repository root. Defaults to cwd.
        keywords: Optional override keyword list. If None, extracted from intent.
        max_candidates: Maximum number of SearchResult objects to return.

    Returns:
        List of SearchResult objects (3-5 candidates, sorted by confidence desc).
        Returns an empty list if no matches found.
    """
    ws = Path(workspace) if workspace is not None else Path.cwd()

    # Extract keywords from intent if not explicitly provided
    if keywords is None:
        kw_from_intent = intent.get("keywords", [])
        capability = intent.get("capability", "")
        target = intent.get("target_subsystem", "")
        # Build keyword list from all sources
        keywords = list(kw_from_intent)
        if capability:
            # Add individual tokens from the capability string
            keywords.extend(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", capability))
        if target:
            keywords.append(target)
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                deduped.append(kw)
        keywords = deduped

    if not keywords:
        logger.debug("spawn_search_subagent: no keywords extracted from intent; returning empty")
        return []

    logger.debug(
        "spawn_search_subagent: searching workspace=%s keywords=%s",
        ws,
        keywords[:5],
    )

    # Run the grep-based locator (the "sub-agent" process)
    raw_matches = _grep_candidates(keywords, ws)

    if not raw_matches:
        logger.debug("spawn_search_subagent: no grep matches found")
        return []

    # Score and group into spans
    results = _group_matches_into_spans(
        raw_matches,
        intent,
        keywords,
        max_candidates=max_candidates,
    )

    logger.debug(
        "spawn_search_subagent: returning %d candidate(s) from %d raw match(es)",
        len(results),
        len(raw_matches),
    )

    return results


def should_use_search_subagent(localizer_symbols: list[dict[str, Any]]) -> bool:
    """Return True when the localizer overflow threshold is exceeded.

    Per the spec: "Bypasses the localizer (F-R7-600) when the localizer
    returns >20 candidate symbols."

    Args:
        localizer_symbols: The list of symbols returned by the localizer.

    Returns:
        True if the search sub-agent should be used instead of the localizer result.
    """
    return len(localizer_symbols) > LOCALIZER_OVERFLOW_THRESHOLD


# Alias required by acceptance criteria (feature 730e0f94).
SearchCandidate = SearchResult


def spawn_search_locator(
    intent: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    keywords: Optional[list[str]] = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[SearchResult]:
    """Spawn a dedicated locator sub-agent and return 3-5 candidate code spans.

    AC-required entry point: 'Function defined:
    bob.brownfield.search_subagent.spawn_search_locator'.

    Implements the WarpGrep v2 pattern: the locator sub-agent's entire job
    is grep → return candidates. Its transcript is conceptually discarded
    after return — only the SearchResult list propagates to the caller.

    Args:
        intent: Feature intent dict with 'capability', 'target_subsystem',
                and 'keywords' fields.
        workspace: Path to the repository root. Defaults to cwd.
        keywords: Optional override keyword list.
        max_candidates: Maximum number of SearchResult objects to return.

    Returns:
        List of SearchResult objects sorted by confidence desc.

    Raises:
        ValueError: If intent is not a dict.
    """
    if not isinstance(intent, dict):
        raise ValueError(f"intent must be a dict, got {type(intent)!r}")
    return spawn_search_subagent(
        intent,
        workspace=workspace,
        keywords=keywords,
        max_candidates=max_candidates,
    )


def spawn_locator_task(
    intent: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    keywords: Optional[list[str]] = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[SearchResult]:
    """Spawn a locator task sub-agent and return candidate code spans.

    This is the AC-required entry point for the WarpGrep search sub-agent
    pattern. Identical to spawn_search_subagent but uses the 'locator task'
    naming from the spec: "Spawn a dedicated 'locator' Task sub-agent whose
    ENTIRE job is grep → return 3-5 (file, span) candidates."

    The locator task's transcript is conceptually discarded after return —
    only the SearchResult list is propagated to the caller.

    Args:
        intent: Feature intent dict with 'capability', 'target_subsystem',
                and 'keywords' fields.
        workspace: Path to the repository root. Defaults to cwd.
        keywords: Optional override keyword list.
        max_candidates: Maximum number of SearchResult objects to return.

    Returns:
        List of SearchResult objects sorted by confidence desc.

    Raises:
        ValueError: If intent is not a dict.
    """
    if not isinstance(intent, dict):
        raise ValueError(f"intent must be a dict, got {type(intent)!r}")
    return spawn_search_subagent(
        intent,
        workspace=workspace,
        keywords=keywords,
        max_candidates=max_candidates,
    )


def locate_candidates(
    intent: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    keywords: Optional[list[str]] = None,
    localizer_symbols: Optional[list[dict[str, Any]]] = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    """Locate 3-5 candidate code spans for a feature (WarpGrep v2 entry point).

    This is the AC-required public entry point for the search sub-agent
    pattern. It spawns the locator sub-agent (grep → candidates), whose
    transcript is discarded, and returns the candidates in the schema
    format: list[{path, start_line, end_line, confidence, rationale_snippet}].

    When ``localizer_symbols`` is supplied and exceeds the overflow threshold
    (>20 symbols), this bypasses the localizer entirely and relies on the
    search sub-agent — the whole point of the WarpGrep pattern. When the
    localizer result is within the threshold, the search sub-agent is still
    run (it is complementary), but callers may prefer the localizer result.

    Args:
        intent: Feature intent dict with 'capability', 'target_subsystem',
                and 'keywords' fields.
        workspace: Repository root. Defaults to cwd.
        keywords: Optional override keyword list.
        localizer_symbols: Optional localizer output used only to decide
                whether the localizer overflowed (informational).
        max_candidates: Maximum number of candidates to return.

    Returns:
        List of candidate dicts (schema-shaped). Empty list if no matches.

    Raises:
        ValueError: If intent is not a dict.
    """
    if not isinstance(intent, dict):
        raise ValueError(f"intent must be a dict, got {type(intent)!r}")

    if localizer_symbols is not None and not should_use_search_subagent(localizer_symbols):
        logger.debug(
            "locate_candidates: localizer returned %d symbol(s) (<= threshold %d); "
            "running search sub-agent as a complement",
            len(localizer_symbols),
            LOCALIZER_OVERFLOW_THRESHOLD,
        )

    results = spawn_search_subagent(
        intent,
        workspace=workspace,
        keywords=keywords,
        max_candidates=max_candidates,
    )
    return [r.to_dict() for r in results]


def filter_candidates_by_confidence(
    candidates: list[SearchResult],
    *,
    min_confidence: float = 0.1,
) -> list[SearchResult]:
    """Filter search candidates by a minimum confidence threshold.

    Returns only candidates whose confidence >= min_confidence, sorted
    descending by confidence. Boundary case: an empty list returns an
    empty list without raising.

    Args:
        candidates: List of SearchResult objects to filter.
        min_confidence: Minimum confidence value (inclusive). Default 0.1.

    Returns:
        Filtered list of SearchResult objects, sorted by confidence desc.

    Raises:
        ValueError: If candidates is not a list.
    """
    if not isinstance(candidates, list):
        raise ValueError(f"candidates must be a list, got {type(candidates)!r}")
    filtered = [c for c in candidates if c.confidence >= min_confidence]
    filtered.sort(key=lambda c: c.confidence, reverse=True)
    return filtered


def multi_candidate_patch(
    feature: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    candidate_count: int = 3,
    patch_generator: Optional[Any] = None,
    test_files: Optional[list[str]] = None,
) -> Any:
    """Run multi-candidate patch generation + LLM-judge vote (AC entry point).

    This is the AC-required entry point for the multi-candidate patch pattern
    (Feature a115f95a). It delegates to
    ``bob.brownfield.multi_candidate_patch.run_multi_candidate``, which:

      1. Gates on ``is_hard_feature`` (difficulty >= 'hard' or prior attempts).
      2. Spawns N=3 worker candidates in parallel worktrees.
      3. Filters out patches that break visible regression tests.
      4. Ranks survivors with the LLM judge.
      5. Commits the winner and archives losers, emitting MULTI_CANDIDATE_WIN.

    Args:
        feature: Feature dict with 'id', 'description', 'acceptance_criteria',
                 'refinement_attempts', 'difficulty', etc.
        workspace: Repository root. Defaults to cwd.
        candidate_count: Number of parallel candidates to spawn (default 3).
        patch_generator: Optional callable(worktree_path, feature) -> str.
        test_files: Optional list of regression test files.

    Returns:
        A MultiCandidateResult with the winning patch and telemetry.

    Raises:
        ValueError: If feature is not a dict.
    """
    if not isinstance(feature, dict):
        raise ValueError(f"feature must be a dict, got {type(feature)!r}")

    from bob.brownfield.multi_candidate_patch import run_multi_candidate

    return run_multi_candidate(
        feature,
        workspace=workspace,
        candidate_count=candidate_count,
        patch_generator=patch_generator,
        test_files=test_files,
    )


def search_results_to_edit_sites(results: list[SearchResult]) -> list[dict[str, Any]]:
    """Convert SearchResult objects to the edit-site format used by the localizer.

    This allows search sub-agent output to be used where localizer edit_sites
    are expected (e.g. in check_disjoint, diff_plan, etc.).

    Args:
        results: List of SearchResult objects from spawn_search_subagent.

    Returns:
        List of edit-site dicts: {path, start_line, end_line, scope, name}.
    """
    return [
        {
            "path": r.path,
            "start_line": r.start_line,
            "end_line": r.end_line,
            "scope": "function",
            "name": "",
        }
        for r in results
    ]
