"""
Feature Extractor — Reads an application spec and generates tasks from scratch.
================================================================================

This is Phase 0 of the planning pipeline: before decomposition evaluates tasks,
we need to GENERATE those tasks by reading the application description, references,
and constraints.

The old pipeline took the spec's existing task list as given. This module replaces
that with an LLM-driven extraction:

  1. Read the application description + references + constraints
  2. Have Opus analyze the codebase requirements
  3. Generate fine-grained, atomic tasks with proper dependency chains
  4. Each generated task includes acceptance criteria, expected outputs, verify scripts

The decomposition engine then evaluates and further refines these generated tasks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bob.orchestrator.claude_executor import execute_task_with_claude

try:
    from bob.orchestrator.claude_sdk_executor import execute_task_with_sdk as _sdk_execute
    _USE_SDK = True
except ImportError:
    _USE_SDK = False


async def _execute(project_dir, prompt, model, timeout_seconds, **kwargs):
    """Execute via SDK (preferred) or CLI (fallback)."""
    if _USE_SDK:
        return await _sdk_execute(
            project_dir=project_dir,
            prompt=prompt,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    return await execute_task_with_claude(
        project_dir=project_dir,
        prompt=prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        **kwargs,
    )


# The main prompt that Opus uses to extract features from the spec
FEATURE_EXTRACTION_PROMPT = """\
You are a principal software architect. Your job is to read an application specification
and decompose it into fine-grained, atomic implementation tasks.

## Application Specification

{spec_description}

## Reference Material

{reference_summaries}

## Constraints

{constraints}

## Environment

Workspace: {workspace_dir}
{environment_notes}

## Your Task

Analyze this specification thoroughly and produce a COMPLETE list of implementation tasks.

### Rules for task decomposition:
1. **Atomic tasks** — Each task should be completable by a single coding agent in one session
   (roughly 30-60 minutes of work, ~200-500 lines of code)
2. **No ambiguity** — Each task's description must be specific enough that an agent can implement
   it without asking clarifying questions
3. **Dependency chains** — Tasks must declare what they depend on. No circular dependencies.
4. **Bottom-up** — Start with foundational data structures, then algorithms, then integration,
   then testing/validation, then documentation
5. **Verify scripts** — Every task needs a verify_script that PROVES the implementation works.
   Not just "file exists" — actual functional tests that catch fake implementations.
6. **Expected outputs** — Every task must list the files it will create/modify with minimum
   line counts and required content patterns
7. **No stubs** — Tasks must produce real, working code. No placeholders, no TODOs, no mocks.

### What to extract:
- Core data structures (classes, interfaces)
- Algorithms and their sub-components
- Integration points between components
- Communication protocols (MPI, networking, etc.)
- Test harnesses and verification scripts
- Benchmarks and performance validation
- Documentation

### Granularity guidance:
- A class with 5+ methods → probably 1 task per major method group, not 1 task for the whole class
- A complex algorithm → break into: core logic, edge cases, optimization, integration
- "Verify X works" → separate task from "implement X"
- Think: "Could a junior developer complete this task in one sitting with clear instructions?"

## Output Format

IMPORTANT: Output the JSON directly to stdout. Do NOT write it to a file. Do NOT use any tools.
Just print the raw JSON object below as your response.

Output ONLY valid JSON (no markdown fences, no commentary):
{{
  "tasks": [
    {{
      "id": "T001",
      "title": "Short descriptive title",
      "description": "Detailed description including:\\n- What to implement\\n- How it should work\\n- Key data structures\\n- Algorithms to use\\n- Edge cases to handle",
      "depends_on": [],
      "priority": "critical|high|medium|low",
      "labels": ["category"],
      "acceptance_criteria": [
        "Specific, testable criterion 1",
        "Specific, testable criterion 2"
      ],
      "expected_outputs": [
        {{
          "path": "src/module/file.py",
          "min_lines": 100,
          "must_contain": ["class ClassName", "def method_name"]
        }}
      ],
      "verify_script": "cd {workspace_dir} && python -c \\"\\nimport ...\\nassert ...\\nprint('OK')\\n\\""
    }}
  ],
  "dependency_graph_summary": "Brief description of the dependency structure",
  "total_estimated_loc": 0
}}
"""


# Prompt for reading reference material and extracting relevant details
REFERENCE_READING_PROMPT = """\
You are a research assistant. Read this reference material and extract key technical details
that are needed to implement the described system.

## Reference

{reference_content}

## Application Context

{app_description}

## Extract:
1. Key algorithms and their mathematical descriptions
2. Data structures and their layouts
3. Communication patterns (MPI, etc.)
4. Numerical values that can be used as test references (energies, tolerances, etc.)
5. Implementation details that affect correctness
6. Performance expectations and scaling behavior

Output a structured summary (plain text, organized by topic).
"""


async def extract_features(
    spec_description: str,
    references: list[dict],
    constraints: list[str],
    workspace_dir: str,
    project_dir: Path,
    model: str = "claude-opus-4-5-20251101",
    timeout_seconds: int = 0,  # 0 = unlimited (planning can take arbitrarily long)
    environment_notes: str = "",
) -> list[dict]:
    """Extract implementation tasks from an application specification.

    This is the core feature extraction: Opus reads the spec description
    and references, then generates a complete list of atomic tasks.

    Args:
        spec_description: The application's description/requirements text
        references: List of reference dicts with 'path', 'label', etc.
        constraints: List of constraint strings
        workspace_dir: Path to workspace directory
        project_dir: Path to project directory
        model: LLM model to use (should be Opus for quality)
        timeout_seconds: Max time for the extraction call
        environment_notes: Additional environment context

    Returns:
        List of task dicts ready to become WorkUnits
    """
    # Step 1: Read reference material (if local files exist)
    reference_summaries = await _read_references(
        references, spec_description, project_dir, model, timeout_seconds,
        workspace_dir=workspace_dir,
    )

    # Step 2: Build the extraction prompt
    constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "None specified."
    ref_text = reference_summaries if reference_summaries else "No reference material provided."

    prompt = FEATURE_EXTRACTION_PROMPT.format(
        spec_description=spec_description,
        reference_summaries=ref_text,
        constraints=constraints_text,
        workspace_dir=workspace_dir,
        environment_notes=environment_notes or "",
    )

    # Step 3: Call Opus
    result = await _execute(
        project_dir=project_dir,
        prompt=prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        non_interactive=True,
        enable_thinking=True,
        stall_timeout=0,  # No stall detection for planning
    )

    if not result.success:
        raise RuntimeError(
            f"Feature extraction failed: {result.error or 'unknown error'}\n"
            f"Output: {result.output[:500] if result.output else '(none)'}"
        )

    # Step 4: Parse the output
    tasks = _parse_tasks(result.output)

    # Fallback: Claude may have written a tasks.json file instead of printing JSON
    if not tasks:
        for candidate in [
            project_dir / "tasks.json",
            Path(workspace_dir) / "tasks.json",
        ]:
            if candidate.exists():
                try:
                    import json as _json
                    data = _json.loads(candidate.read_text())
                    tasks = data.get("tasks", data if isinstance(data, list) else [])
                    if tasks:
                        # Clean up the file
                        candidate.unlink(missing_ok=True)
                        break
                except Exception:
                    continue

    if not tasks:
        raise RuntimeError(
            f"Feature extraction produced no tasks.\n"
            f"Output: {result.output[:1000] if result.output else '(none)'}"
        )

    return tasks


async def _read_references(
    references: list[dict],
    app_description: str,
    project_dir: Path,
    model: str,
    timeout_seconds: int,
    workspace_dir: str = "",
) -> str:
    """Read and summarize reference materials.

    For each reference with a local file path, read the content and
    have Claude extract relevant technical details.
    """
    if not references:
        return ""

    summaries = []

    for ref in references:
        label = ref.get("label", ref.get("path", "unknown"))
        path = ref.get("path", "")

        if not path:
            summaries.append(f"### {label}\n(No path provided)\n")
            continue

        # Resolve relative paths — try workspace first, then project dir
        full_path = Path(path)
        if not full_path.is_absolute():
            ws_path = Path(workspace_dir) / path if workspace_dir else None
            proj_path = project_dir / path
            if ws_path and ws_path.exists():
                full_path = ws_path
            elif proj_path.exists():
                full_path = proj_path
            else:
                full_path = ws_path or proj_path  # Use workspace path for error message

        if not full_path.exists():
            summaries.append(f"### {label}\n(File not found: {full_path})\n")
            continue

        # Read the file (handle PDFs specially)
        try:
            if full_path.suffix.lower() == ".pdf":
                # Use pdftotext for PDF files (falls back to error message)
                import subprocess
                try:
                    result = subprocess.run(
                        ["pdftotext", "-layout", str(full_path), "-"],
                        capture_output=True, text=True, timeout=30,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        content = result.stdout
                    else:
                        summaries.append(f"### {label}\n(Failed to extract PDF text: {result.stderr.strip()})\n")
                        continue
                except FileNotFoundError:
                    summaries.append(f"### {label}\n(pdftotext not installed — cannot read PDF)\n")
                    continue
                except subprocess.TimeoutExpired:
                    summaries.append(f"### {label}\n(PDF extraction timed out)\n")
                    continue
            else:
                content = full_path.read_text(errors="replace")
            # Strip null bytes that can corrupt API calls
            content = content.replace("\x00", "")
            # Truncate very long files
            if len(content) > 50000:
                content = content[:50000] + "\n\n[... truncated at 50K chars ...]"
        except Exception as e:
            summaries.append(f"### {label}\n(Error reading: {e})\n")
            continue

        # For short files, include directly; for long ones, summarize
        if len(content) < 5000:
            summaries.append(f"### {label}\n{content}\n")
        else:
            # Have Claude summarize
            summary_prompt = REFERENCE_READING_PROMPT.format(
                reference_content=content,
                app_description=app_description[:2000],
            )

            result = await _execute(
                project_dir=project_dir,
                prompt=summary_prompt,
                model=model,
                timeout_seconds=timeout_seconds,  # no artificial cap on reference reading
                non_interactive=True,
                enable_thinking=True,
                stall_timeout=0,
            )

            if result.success and result.output:
                summaries.append(f"### {label}\n{result.output}\n")
            else:
                # Fallback: include first + last portion
                summaries.append(
                    f"### {label}\n"
                    f"{content[:3000]}\n\n[...middle omitted...]\n\n{content[-2000:]}\n"
                )

    return "\n\n".join(summaries)


def _parse_tasks(output: str) -> list[dict]:
    """Parse task list from Claude's JSON output.

    Handles various output formats:
    - Clean JSON
    - JSON wrapped in markdown fences
    - JSON mixed with commentary
    """
    if not output:
        return []

    # Try to find JSON in the output
    text = output.strip()

    # Strip markdown fences
    text = re.sub(r'^```(?:json)?\s*\n', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n```\s*$', '', text, flags=re.MULTILINE)

    # Try direct parse
    try:
        data = json.loads(text)
        return data.get("tasks", [])
    except json.JSONDecodeError:
        pass

    # Try finding the JSON object
    brace_start = text.find('{')
    if brace_start == -1:
        return []

    # Find matching closing brace
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[brace_start:i + 1])
                    return data.get("tasks", [])
                except json.JSONDecodeError:
                    pass
                break

    # Last resort: try to find a JSON array of tasks
    bracket_start = text.find('[')
    if bracket_start != -1:
        depth = 0
        for i in range(bracket_start, len(text)):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[bracket_start:i + 1])
                    except json.JSONDecodeError:
                        pass
                    break

    return []


def extract_spec_metadata(spec_data: dict) -> tuple[str, list[str], str]:
    """Extract description, constraints, and environment notes from a spec dict.

    Builds a comprehensive description from all available spec fields:
    - name
    - description
    - defaults
    - references (as context)
    - Any existing tasks (as hints, not constraints)

    Returns:
        (full_description, constraints_list, environment_notes)
    """
    parts = []

    # Name
    name = spec_data.get("name", "")
    if name:
        parts.append(f"# {name}\n")

    # Description
    desc = spec_data.get("description", "")
    if desc:
        parts.append(desc)

    # If there are existing tasks, include them as "reference implementation hints"
    # but explicitly tell the LLM not to be bound by them
    existing_tasks = spec_data.get("tasks", [])
    if existing_tasks:
        parts.append("\n## Previous Task Breakdown (for reference only — generate your own)")
        parts.append("The following tasks were previously defined. Use them as hints for")
        parts.append("what the system needs, but generate your own task list with finer")
        parts.append("granularity and better decomposition:\n")
        for t in existing_tasks:
            tid = t.get("id", "?")
            title = t.get("title", "")
            desc = t.get("description", "")[:200]
            parts.append(f"- **{tid}: {title}** — {desc}")

    full_description = "\n".join(parts)

    # Extract constraints from description
    constraints = []
    for line in desc.split("\n"):
        line_lower = line.strip().lower()
        if any(kw in line_lower for kw in [
            "must not", "do not", "forbidden", "critical requirement",
            "policy", "not allowed", "never", "only allowed",
        ]):
            constraints.append(line.strip())

    # Extract from defaults
    defaults = spec_data.get("defaults", {})
    if defaults:
        for k, v in defaults.items():
            if k not in ("priority",):
                constraints.append(f"Default {k}: {v}")

    # Environment notes
    env_parts = []
    if "environment" in spec_data:
        env = spec_data["environment"]
        if isinstance(env, dict):
            for k, v in env.items():
                env_parts.append(f"{k}: {v}")
        elif isinstance(env, str):
            env_parts.append(env)

    environment_notes = "\n".join(env_parts)

    return full_description, constraints, environment_notes
