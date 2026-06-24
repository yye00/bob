"""Sub-agent orientation protocol with bob memory (F107) and progress notes (F108).

Provides mandatory orientation context for all Bob sub-agents. Every
sub-agent starts by running a series of orientation steps to recover
project context, and optionally queries bob memory for relevant
knowledge.

F108 adds session continuity via claude-progress.txt:
- update_progress_notes() writes structured entries after each sub-agent session
- read_progress_notes() reads the file for orientation context
- Entries are trimmed to keep only the last MAX_PROGRESS_ENTRIES (10)

Usage::

    from bob.orientation import wrap_prompt_with_orientation

    # Wrap a task prompt with full orientation
    oriented_prompt = wrap_prompt_with_orientation(
        prompt="Implement feature X ...",
        feature_id="F107",
        workspace="/path/to/workspace",
    )

    # On retry, add debugging protocol
    oriented_prompt = wrap_prompt_with_orientation(
        prompt="Implement feature X ...",
        feature_id="F107",
        workspace="/path/to/workspace",
        is_retry=True,
    )

    # After a sub-agent session, update progress notes
    from bob.orientation import update_progress_notes
    update_progress_notes(
        workspace="/path/to/workspace",
        feature_id="F108",
        feature_name="Progress notes",
        outcome="completed",
        duration_ms=5000,
        cost_usd=0.50,
    )

Bootstrap detection: Features F016 and F017 (memory integration itself)
skip all memory operations since the memory system doesn't exist yet
when those features are being implemented.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Feature IDs that represent memory bootstrapping — bob memory is not
# available yet when these features are being implemented.
BOOTSTRAP_FEATURE_IDS: frozenset[str] = frozenset({"F016", "F017"})

# Maximum number of progress entries to keep in claude-progress.txt (F108).
MAX_PROGRESS_ENTRIES: int = 10

PROGRESS_FILENAME: str = "claude-progress.txt"
ENTRY_SEPARATOR: str = "---"


# ============================================================
# F108: Progress notes between sessions
# ============================================================


def format_progress_entry(
    *,
    feature_id: str,
    feature_name: str,
    outcome: str,
    duration_ms: int | None = None,
    num_turns: int | None = None,
    cost_usd: float | None = None,
    blockers: str | None = None,
    notes: str | None = None,
) -> str:
    """Format a single progress entry for claude-progress.txt.

    Produces a structured text block with key-value pairs separated
    by a ``---`` delimiter at the end.

    Args:
        feature_id: The feature ID that was worked on.
        feature_name: Human-readable feature name.
        outcome: Result of the session (completed/failed/interrupted).
        duration_ms: Optional execution duration in milliseconds.
        num_turns: Optional number of agent turns used.
        cost_usd: Optional cost in USD.
        blockers: Optional description of blockers encountered.
        notes: Optional free-form session notes.

    Returns:
        A formatted entry string ending with ``---``.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"timestamp: {timestamp}",
        f"feature_id: {feature_id}",
        f"feature_name: {feature_name}",
        f"outcome: {outcome}",
    ]

    if duration_ms is not None:
        lines.append(f"duration_ms: {duration_ms}")
    if num_turns is not None:
        lines.append(f"num_turns: {num_turns}")
    if cost_usd is not None:
        lines.append(f"cost_usd: {cost_usd}")
    if blockers is not None:
        lines.append(f"blockers: {blockers}")
    if notes is not None:
        lines.append(f"notes: {notes}")

    lines.append(ENTRY_SEPARATOR)
    return "\n".join(lines)


def _parse_entries(content: str) -> list[str]:
    """Split the progress file content into individual entries.

    Each entry is delimited by a line containing only ``---``.
    Returns a list of entry strings (without trailing separators).
    """
    if not content.strip():
        return []

    # Split on the separator line
    raw_blocks = content.split(ENTRY_SEPARATOR)
    entries = []
    for block in raw_blocks:
        stripped = block.strip()
        if stripped:
            entries.append(stripped)
    return entries


def update_progress_notes(
    *,
    workspace: str,
    feature_id: str,
    feature_name: str,
    outcome: str,
    duration_ms: int | None = None,
    num_turns: int | None = None,
    cost_usd: float | None = None,
    blockers: str | None = None,
    notes: str | None = None,
) -> None:
    """Append a progress entry to claude-progress.txt, keeping last N entries.

    Creates the file if it does not exist. After appending, trims old
    entries so that at most ``MAX_PROGRESS_ENTRIES`` entries remain.

    Args:
        workspace: Path to the project workspace directory.
        feature_id: The feature ID that was worked on.
        feature_name: Human-readable feature name.
        outcome: Result of the session (completed/failed/interrupted).
        duration_ms: Optional execution duration in milliseconds.
        num_turns: Optional number of agent turns used.
        cost_usd: Optional cost in USD.
        blockers: Optional description of blockers encountered.
        notes: Optional free-form session notes.
    """
    progress_path = pathlib.Path(workspace) / PROGRESS_FILENAME

    # Read existing content
    existing = ""
    if progress_path.exists():
        existing = progress_path.read_text()

    # Parse existing entries
    entries = _parse_entries(existing)

    # Format and append the new entry
    new_entry = format_progress_entry(
        feature_id=feature_id,
        feature_name=feature_name,
        outcome=outcome,
        duration_ms=duration_ms,
        num_turns=num_turns,
        cost_usd=cost_usd,
        blockers=blockers,
        notes=notes,
    )
    # The new_entry already ends with ---, split it back to get the content.
    # NOTE: ``rstrip(ENTRY_SEPARATOR)`` would treat the argument as a SET of
    # chars and strip any trailing '-', silently truncating content like
    # '--verbose' or 'something-'. ``removesuffix`` (Python 3.9+) strips the
    # literal string instead.
    new_entry_content = (
        new_entry.removesuffix("\n" + ENTRY_SEPARATOR)
        .removesuffix(ENTRY_SEPARATOR)
        .rstrip("\n")
        .strip()
    )
    entries.append(new_entry_content)

    # Trim to keep only the last MAX_PROGRESS_ENTRIES
    if len(entries) > MAX_PROGRESS_ENTRIES:
        entries = entries[-MAX_PROGRESS_ENTRIES:]

    # Write back: each entry followed by ---
    output_lines = []
    for entry in entries:
        output_lines.append(entry)
        output_lines.append(ENTRY_SEPARATOR)

    progress_path.write_text("\n".join(output_lines) + "\n")
    logger.debug("Updated progress notes at %s (%d entries)", progress_path, len(entries))

    # Emit a structured event alongside the text write so both streams stay in sync.
    try:
        from bob.progress_events import emit_event

        payload: dict = {
            "feature_name": feature_name,
            "outcome": outcome,
            "blockers": blockers,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if num_turns is not None:
            payload["num_turns"] = num_turns
        if cost_usd is not None:
            payload["cost_usd"] = cost_usd
        if notes is not None:
            payload["notes"] = notes

        emit_event(
            event_type="progress_updated",
            payload=payload,
            project_id="",
            feature_id=feature_id,
            attempt_number=0,
        )
    except Exception:
        logger.debug("Failed to emit structured progress event for %s", feature_id, exc_info=True)


def read_progress_notes(*, workspace: str) -> str:
    """Read the contents of claude-progress.txt.

    Returns the full file content, or an empty string if the file
    does not exist.

    Args:
        workspace: Path to the project workspace directory.

    Returns:
        The file contents as a string, or empty string if missing.
    """
    progress_path = pathlib.Path(workspace) / PROGRESS_FILENAME
    if not progress_path.exists():
        return ""
    return progress_path.read_text()


def is_bootstrap_feature(feature_id: str | None) -> bool:
    """Check whether a feature is a bob memory bootstrap feature.

    Bootstrap features (F016, F017) cannot use bob memory because
    they are the features that implement memory integration itself.

    Args:
        feature_id: The feature ID to check, or None.

    Returns:
        True if the feature is F016 or F017, False otherwise.
    """
    if not feature_id:
        return False
    return feature_id in BOOTSTRAP_FEATURE_IDS


def get_memory_search_prompt(
    feature_id: str,
    feature_name: str,
    feature_description: str,
) -> str:
    """Generate Bob memory search commands for feature context.

    Creates a prompt section that instructs the sub-agent to search
    Bob Memory across three pools: lessons, facts, and context.

    Args:
        feature_id: The feature ID being worked on.
        feature_name: Human-readable feature name.
        feature_description: Description of what the feature does.

    Returns:
        A prompt string with memory_search commands for all three pools.
    """
    return (
        f"## Search for Relevant Knowledge ({feature_id})\n\n"
        f"Use Bob Memory to search for relevant past knowledge:\n\n"
        f"### Search lessons pool:\n"
        f'memory_search("lessons {feature_id} {feature_name}")\n\n'
        f"### Search facts pool:\n"
        f'memory_search("facts {feature_description}")\n\n'
        f"### Search context pool:\n"
        f'memory_search("context project state")\n'
        f'memory_search("context recent changes")\n'
    )


def get_orientation_prompt(
    feature_id: str,
    workspace: str,
    *,
    is_retry: bool = False,
    feature_name: str | None = None,
    feature_description: str | None = None,
) -> str:
    """Generate the mandatory orientation prompt for a sub-agent.

    Every sub-agent starts with these steps:
    1. pwd && ls -la
    2. cat app_spec.txt | head -100
    3. Query feature status
    4. cat claude-progress.txt
    5. git log --oneline -10
    6. memory_search for relevant knowledge (if not bootstrap)

    On retry, also applies the systematic debugging protocol and
    searches for past fixes.

    Args:
        feature_id: The feature being worked on.
        workspace: Path to the project workspace.
        is_retry: If True, adds debugging protocol and past-fix search.
        feature_name: Optional feature name for Bob memory searches.
        feature_description: Optional feature description for Bob memory searches.

    Returns:
        The orientation prompt string.
    """
    bootstrap = is_bootstrap_feature(feature_id)

    sections = [
        f"# MANDATORY ORIENTATION - DO NOT SKIP\n\n"
        f"You are a sub-agent working on feature {feature_id}. Before you begin,\n"
        f"you MUST complete the following orientation steps.\n\n"
        f"Workspace: {workspace}\n",
        "## Step 1: Understand Working Directory\n"
        "```bash\n"
        "pwd\n"
        "ls -la\n"
        "```\n",
        "## Step 2: Read Project Specification\n"
        "```bash\n"
        "cat app_spec.txt | head -100\n"
        "```\n",
        f"## Step 3: Query Feature Status\n"
        f"Check the current status of feature {feature_id} in the database.\n",
        "## Step 4: Read Progress Notes\n"
        "```bash\n"
        "cat claude-progress.txt\n"
        "```\n",
        "## Step 5: Recent Git History\n"
        "```bash\n"
        "git log --oneline -10\n"
        "```\n",
    ]

    # Step 6: Bob memory search (skip for bootstrap features)
    if bootstrap:
        sections.append(
            "## Step 6: Bob Memory Search (SKIPPED - Bootstrap Feature)\n\n"
            f"Feature {feature_id} is a bootstrap feature that implements memory\n"
            "integration itself. Skipping memory operations since the\n"
            "memory system does not exist yet.\n"
        )
    else:
        name = feature_name or feature_id
        desc = feature_description or f"Feature {feature_id}"
        memory_prompt = get_memory_search_prompt(feature_id, name, desc)
        sections.append(f"## Step 6: Bob Memory Search\n\n{memory_prompt}\n")

    # Retry additions: debugging protocol + past fix search
    if is_retry:
        retry_section = (
            "## RETRY MODE: Systematic Debugging Protocol\n\n"
            "This is a retry attempt. A previous attempt at this feature failed.\n"
            "Apply the systematic debugging protocol:\n\n"
            "1. What was the exact error or failure from the previous attempt?\n"
            "2. What was the expected behavior vs. actual behavior?\n"
            "3. What code/component is involved in the failure?\n"
            "4. Form a hypothesis about the root cause.\n"
            "5. Implement a fix that addresses the root cause.\n\n"
        )
        if not bootstrap:
            retry_section += (
                "### Search for previous fixes and lessons:\n"
                f'memory_search("lessons fix {feature_id}")\n'
                f'memory_search("lessons previous failure {feature_id}")\n'
            )
        else:
            retry_section += (
                "### Search for previous fixes:\n"
                "Review git log for previous fix attempts related to this feature.\n"
            )
        sections.append(retry_section)

    return "\n".join(sections)


def wrap_prompt_with_orientation(
    prompt: str,
    feature_id: str,
    workspace: str,
    *,
    is_retry: bool = False,
    feature_name: str | None = None,
    feature_description: str | None = None,
    enable_tdd: bool = False,
    enable_verification: bool = True,
    enable_subagent: bool = False,
) -> str:
    """Wrap a task prompt with full orientation context.

    Prepends the mandatory orientation steps to the given task prompt,
    appends Superpowers skill sections (F113), and appends post-completion
    memory storage instructions for non-bootstrap features.

    Args:
        prompt: The original task prompt to wrap.
        feature_id: The feature being worked on.
        workspace: Path to the project workspace.
        is_retry: If True, adds debugging protocol.
        feature_name: Optional feature name for Bob memory searches.
        feature_description: Optional feature description for Bob memory searches.
        enable_tdd: If True, adds TDD mode instructions (F113).
        enable_verification: If True, adds verification checklist (F113, default True).
        enable_subagent: If True, adds sub-agent driven development (F113).

    Returns:
        The wrapped prompt with orientation prepended.
    """
    from bob.superpowers import (
        build_superpowers_prompt,
        get_superpowers_orientation,
    )

    orientation = get_orientation_prompt(
        feature_id=feature_id,
        workspace=workspace,
        is_retry=is_retry,
        feature_name=feature_name,
        feature_description=feature_description,
    )

    # F113: Append Superpowers skills documentation to orientation
    superpowers_orientation = get_superpowers_orientation()

    # F113: Build active superpowers prompt sections
    superpowers_prompt = build_superpowers_prompt(
        enable_tdd=enable_tdd,
        enable_verification=enable_verification,
        enable_subagent=enable_subagent,
    )

    parts = [orientation, superpowers_orientation]

    if superpowers_prompt:
        parts.append(superpowers_prompt)

    parts.append("---\n# NOW BEGIN YOUR TASK\n")
    parts.append(prompt)

    # Add post-completion instructions
    post = get_post_completion_prompt(feature_id)
    if post:
        parts.append("\n---\n" + post)

    return "\n".join(parts)


def wrap_researcher_prompt(
    path_glob: str,
    symbol_shortlist: list[str],
    feature_id: str,
    workspace: str,
) -> str:
    """Wrap a researcher sub-agent prompt with the hide-the-ticket constraint.

    Integrates the BF-2 researcher role (bob.agents.roles.RESEARCHER) with
    the orientation protocol.  The researcher sub-agent receives ONLY the
    path_glob and symbol_shortlist — no ticket/intent text is passed.

    Args:
        path_glob:        Subsystem path glob from the localizer.
        symbol_shortlist: Symbol names from survey.db to focus on.
        feature_id:       UUID of the feature being researched.
        workspace:        Path to the project workspace.

    Returns:
        Wrapped researcher prompt string with orientation prepended and
        hide-the-ticket instruction enforced.
    """
    from bob.agents.roles import build_researcher_prompt

    researcher_prompt = build_researcher_prompt(path_glob, symbol_shortlist)
    orientation = get_orientation_prompt(
        feature_id=feature_id,
        workspace=workspace,
        feature_name=f"researcher-{feature_id}",
        feature_description="Researcher sub-agent: document code without seeing ticket intent.",
    )
    return "\n".join([orientation, "---\n# RESEARCHER TASK (hide-the-ticket)\n", researcher_prompt])


def get_post_completion_prompt(feature_id: str) -> str:
    """Generate post-completion memory storage instructions.

    After completing a task, sub-agents should store new knowledge
    in Bob Memory for future agents to benefit from.

    Bootstrap features (F016/F017) skip this since memory is not
    available yet.

    Args:
        feature_id: The feature that was completed.

    Returns:
        A prompt string with post-completion instructions, or empty
        string for bootstrap features.
    """
    if is_bootstrap_feature(feature_id):
        return ""

    return (
        f"## Post-Completion: Store Knowledge ({feature_id})\n\n"
        "After completing your task successfully, store knowledge for future agents:\n\n"
        "1. Store any new facts learned:\n"
        "   ```\n"
        '   memory_add("New fact about [technology/pattern]", pool="facts")\n'
        "   ```\n\n"
        "2. Store lessons from debugging or failures:\n"
        "   ```\n"
        "   memory_add(\n"
        '       "TRIGGER: [what triggered]\\n'\
        'LESSON: [what you learned]\\n'\
        'SOLUTION: [how you solved it]",\n'
        '       pool="lessons"\n'
        "   )\n"
        "   ```\n\n"
        "3. Record feedback on memories that helped:\n"
        "   ```\n"
        "   memory_record_feedback(memory_id=\"mem_xxx\", success=True)\n"
        "   ```\n"
    )
