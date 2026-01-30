"""
Verification Researcher — Phase 1.5
====================================

Reads reference papers and searches Perplexity to auto-generate
verification tests for scientific computing tasks.

This is Phase 1.5 in the planning pipeline:
  Phase 1:   PLAN    — Generate tasks with confidence scores
  Phase 1.5: VERIFY  — Generate verification tests from papers + search
  Phase 2:   REFINE  — Loop until confidence > threshold
  Phase 3:   VALIDATE — Syntax-check scripts, reject trivial tests

For each task with verification_level="scientific", this module:
1. Extracts relevant sections from reference papers
2. Searches Perplexity for supplementary reference values
3. Generates numerical_tests, algorithmic_tests, convergence_tests
4. Each test has a `source` field documenting where values came from

The generated tests are stored in the spec YAML and synced to the DB.
The coding agent cannot modify them — it must write code that passes.
"""

import json
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Optional

from bob.orchestrator.claude_executor import execute_task_with_claude


# ---------------------------------------------------------------------------
# Prompt template for verification test generation
# ---------------------------------------------------------------------------

VERIFICATION_RESEARCH_PROMPT = """\
You are a verification test engineer for scientific computing software.

Your job: Generate tests that will CATCH fake or incorrect implementations.
These tests will be stored in a database and the coding agent CANNOT modify
them. The coding agent must write real code that passes these tests.

## Task Under Test

**Title:** {task_title}
**Description:**
{task_description}

**Acceptance Criteria:**
{acceptance_criteria}

**Constraints (must_not_contain):**
{constraints}

**Expected Output Files:**
{expected_outputs}

## Reference Material

### From Papers
{paper_context}

### From Search
{search_context}

## Workspace

Working directory: {workspace_dir}
Python path includes workspace root.
Import paths use: `from src.distributed.module import Class`

## What You Must Generate

Generate THREE categories of verification tests as JSON.

### 1. numerical_tests
Known-answer tests with tight tolerances. These catch:
- Hardcoded return values (return -4.0)
- Wrong algorithms that give wrong numbers
- Off-by-one errors in indexing

Requirements:
- Use reference values from the papers or search results
- Include the source of each reference value
- Tolerances should be tight but realistic (1e-4 for energies, 1e-6 for norms)
- Test with MULTIPLE inputs (different L, different parameters)
- If a test computes its own reference (e.g., exact diagonalization for small L),
  include that computation IN the test command

### 2. algorithmic_tests
Verify the METHOD, not just the answer. These catch:
- Wrapping an existing library (e.g., calling quimb internally)
- Copy-pasting reference values
- Trivial implementations that happen to pass numerical tests

Techniques:
- **Dependency blocking:** Monkey-patch forbidden imports to raise errors,
  then run the code. It must still work.
- **Differential testing:** Different inputs MUST give different outputs.
  If J=1.0 gives energy E1 and J=2.0 gives energy E2, then E1 != E2.
- **Structural checks:** The code must use specific algorithmic steps
  (e.g., SVD truncation, environment contraction)

### 3. convergence_tests
Verify the algorithm behaves correctly as a PROCESS. These catch:
- Algorithms that converge to wrong values
- Implementations that don't actually iterate
- Hardcoded iteration counts with random noise

Properties to test:
- Energy decreases (or stays same) with each sweep
- Higher bond dimension gives lower (better) energy
- More sweeps gives better convergence
- Algorithm reaches a stable fixed point (not oscillating)
- For parallel: more overlap or boundary sweeps → better results

## Output Format

Output ONLY valid JSON. No markdown fences. No text outside JSON.

```
{{
  "numerical_tests": [
    {{
      "name": "descriptive_test_name",
      "command": "cd {workspace_dir} && python -c \\"\\n... python code ...\\nprint('PASS: description')\\n\\"",
      "timeout": 60,
      "source": "Where the reference value came from (paper name + section, or search result)"
    }}
  ],
  "algorithmic_tests": [
    {{
      "name": "descriptive_test_name",
      "command": "cd {workspace_dir} && python -c \\"\\n... python code ...\\nprint('PASS: description')\\n\\"",
      "timeout": 120,
      "source": "What algorithmic property this verifies"
    }}
  ],
  "convergence_tests": [
    {{
      "name": "descriptive_test_name",
      "command": "cd {workspace_dir} && python -c \\"\\n... python code ...\\nprint('PASS: description')\\n\\"",
      "timeout": 180,
      "source": "What convergence property this verifies"
    }}
  ]
}}
```

CRITICAL RULES:
- Every command must be a valid bash one-liner that runs Python
- Every test must print 'PASS: ...' on success or raise/assert on failure
- Tests must be SELF-CONTAINED — no external test fixtures
- Numerical tests MUST include at least 2 different parameter sets
- Algorithmic tests MUST include at least 1 dependency-blocking test
- Convergence tests MUST verify monotonic improvement of some metric
- Use realistic imports based on the expected output file paths
- The workspace_dir is: {workspace_dir}

Generate the tests now.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_paper_text(paper_path: Path, sections: list[str] | None = None) -> str:
    """Extract text from a PDF, optionally filtering to specific sections.

    Uses pdftotext (poppler-utils) for extraction. Falls back to
    PyPDF2/pypdf if pdftotext is not available.

    Args:
        paper_path: Path to PDF file
        sections: Optional list of section names to extract

    Returns:
        Extracted text (full or section-filtered)
    """
    if not paper_path.exists():
        return f"[Paper not found: {paper_path}]"

    text = ""

    # Try pdftotext first (best quality)
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(paper_path), "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            text = result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: PyPDF2 / pypdf
    if not text:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(paper_path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(paper_path))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                return f"[Cannot extract PDF — install poppler-utils or pypdf]"

    if not text.strip():
        return f"[Empty text extracted from {paper_path.name}]"

    # If no section filter, return full text (truncated)
    if not sections:
        # Limit to ~8K chars (~2K tokens) to keep context manageable
        if len(text) > 8000:
            text = text[:8000] + "\n\n[... truncated ...]"
        return text

    # Extract specific sections by matching headings
    extracted = []
    lines = text.split("\n")
    capturing = False
    current_section = ""

    for line in lines:
        stripped = line.strip()

        # Check if this line matches a requested section heading
        for section in sections:
            # Match various heading formats: "II. Parallel Algorithm",
            # "Section II: Parallel Algorithm", "2. Parallel Algorithm", etc.
            section_lower = section.lower()
            # Remove common prefixes for matching
            clean_section = re.sub(
                r'^(section\s+)?([\divxlc]+[\.\:\s]+)?',
                '', section_lower
            ).strip()

            if clean_section and clean_section in stripped.lower():
                capturing = True
                current_section = section
                extracted.append(f"\n### {section}\n")
                break

        if capturing:
            extracted.append(line)

            # Stop capturing at next major heading (heuristic)
            if (
                stripped
                and len(stripped) < 80
                and stripped[0].isupper()
                and stripped != current_section
                and re.match(r'^[IVX\d]+[\.\:\s]', stripped)
                and len(extracted) > 10
            ):
                capturing = False

    if extracted:
        result = "\n".join(extracted)
        if len(result) > 8000:
            result = result[:8000] + "\n\n[... truncated ...]"
        return result

    # If section extraction failed, return truncated full text
    if len(text) > 8000:
        text = text[:8000] + "\n\n[... truncated ...]"
    return text


def _format_acceptance_criteria(criteria: list[str]) -> str:
    """Format acceptance criteria as a bulleted list."""
    if not criteria:
        return "(none specified)"
    return "\n".join(f"- {c}" for c in criteria)


def _format_constraints(task_data: dict) -> str:
    """Extract constraints from task data (must_not_contain, spec requirements)."""
    constraints = []

    # From expected outputs' must_not_contain
    for output in task_data.get("expected_outputs", []):
        if isinstance(output, dict):
            for pattern in output.get("must_not_contain", []):
                constraints.append(f"Code must NOT contain: {pattern}")

    # From description
    desc = task_data.get("description", "")
    if "must not" in desc.lower() or "do not" in desc.lower():
        # Extract constraint sentences
        for sentence in desc.split("."):
            if any(kw in sentence.lower() for kw in ["must not", "do not", "forbidden", "prohibited", "not allowed"]):
                constraints.append(sentence.strip())

    return "\n".join(f"- {c}" for c in constraints) if constraints else "(none specified)"


def _format_expected_outputs(outputs: list) -> str:
    """Format expected outputs as a readable list."""
    if not outputs:
        return "(none specified)"
    lines = []
    for o in outputs:
        if isinstance(o, dict):
            path = o.get("path", "?")
            min_lines = o.get("min_lines", 0)
            must_contain = o.get("must_contain", [])
            line = f"- {path}"
            if min_lines:
                line += f" (>={min_lines} lines)"
            if must_contain:
                line += f" [must contain: {', '.join(must_contain[:3])}]"
            lines.append(line)
        elif isinstance(o, str):
            lines.append(f"- {o}")
    return "\n".join(lines)


def _parse_test_output(output: str) -> dict:
    """Parse Claude's JSON output into test categories."""
    # Strip markdown fences
    text = output.strip()
    text = re.sub(r'^```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    text = text.strip()

    # Try to parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from larger text
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}
        else:
            return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}

    # Validate structure
    result = {
        "numerical_tests": [],
        "algorithmic_tests": [],
        "convergence_tests": [],
    }

    for category in result:
        tests = data.get(category, [])
        for test in tests:
            if isinstance(test, dict) and "name" in test and "command" in test:
                result[category].append({
                    "name": test["name"],
                    "command": test["command"],
                    "timeout": test.get("timeout", 120),
                    "source": test.get("source", "auto-generated"),
                })

    return result


# ---------------------------------------------------------------------------
# Main Researcher Class
# ---------------------------------------------------------------------------

class VerificationResearcher:
    """
    Auto-generates verification tests by reading reference papers
    and searching for domain-specific reference values.

    This is Phase 1.5 in BOB's planning pipeline. For each task
    with verification_level="scientific", it:
    1. Extracts relevant sections from reference PDFs
    2. Searches Perplexity for supplementary values (via Claude's MCP)
    3. Generates numerical, algorithmic, and convergence tests

    The tests are stored in the spec YAML, synced to the DB, and
    are immutable by the coding agent.
    """

    def __init__(
        self,
        workspace_dir: str,
        project_dir: Path,
        references: list[dict] | None = None,
        model: str = "claude-sonnet-4-5-20250929",
        timeout_seconds: int = 300,
        enable_research: bool = True,
    ):
        """
        Args:
            workspace_dir: Project workspace directory
            project_dir: Project directory for Claude execution
            references: Reference documents from spec YAML
            model: Model to use for test generation
            timeout_seconds: Timeout per task research call
            enable_research: Whether to enable Perplexity MCP for web search
        """
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.references = references or []
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enable_research = enable_research

    def _get_relevant_papers(self, task_data: dict) -> str:
        """Extract paper text relevant to a specific task.

        Matches task labels/title against reference labels to find
        relevant papers, then extracts relevant sections.
        """
        if not self.references:
            return "(no reference documents provided)"

        paper_texts = []

        for ref in self.references:
            path = ref.get("path")
            if not path:
                continue

            paper_path = Path(self.workspace_dir) / path
            sections = ref.get("sections")
            label = ref.get("label", path)
            is_focus = ref.get("focus", False)

            # Always include focus references
            # For non-focus, check if task might be related
            if not is_focus:
                # Simple heuristic: check if any keywords overlap
                task_text = (
                    task_data.get("title", "") + " " +
                    task_data.get("description", "")
                ).lower()
                ref_label = label.lower()
                # Check for keyword overlap
                ref_words = set(re.findall(r'\w+', ref_label))
                task_words = set(re.findall(r'\w+', task_text))
                overlap = ref_words & task_words - {"the", "a", "an", "of", "in", "for", "and", "to", "with"}
                if len(overlap) < 2:
                    continue

            text = _extract_paper_text(paper_path, sections)
            paper_texts.append(f"#### {label}\n{text}")

        return "\n\n".join(paper_texts) if paper_texts else "(no relevant papers found)"

    def _build_search_context(self, task_data: dict) -> str:
        """Build search context placeholder.

        The actual search happens inside Claude via Perplexity MCP.
        We include search guidance in the prompt so Claude knows what to look for.
        """
        if not self.enable_research:
            return "(web search disabled)"

        # Generate search queries based on task
        title = task_data.get("title", "")
        desc = task_data.get("description", "")

        queries = []
        # Look for domain-specific terms
        if any(kw in desc.lower() for kw in ["energy", "eigenvalue", "ground state", "hamiltonian"]):
            queries.append(f"exact ground state energy {title}")
        if any(kw in desc.lower() for kw in ["convergence", "sweep", "iteration"]):
            queries.append(f"convergence properties {title}")
        if any(kw in desc.lower() for kw in ["scaling", "parallel", "distributed"]):
            queries.append(f"parallel scaling benchmarks {title}")

        if queries:
            return (
                "Use Perplexity to search for reference values. Suggested queries:\n" +
                "\n".join(f"- {q}" for q in queries) +
                "\n\nInclude any numerical values you find in the tests."
            )
        return "(no specific search guidance — use your domain knowledge)"

    async def research_task(self, task_data: dict) -> dict:
        """Generate verification tests for a single task.

        Args:
            task_data: Task dict from the plan (with id, title, description, etc.)

        Returns:
            Dict with numerical_tests, algorithmic_tests, convergence_tests
        """
        task_id = task_data.get("id", "???")
        title = task_data.get("title", "Unknown task")

        print(f"\n  🔬 Researching verification for {task_id}: {title}")

        # Build context from papers
        paper_context = self._get_relevant_papers(task_data)

        # Build search context
        search_context = self._build_search_context(task_data)

        # Format the prompt
        prompt = VERIFICATION_RESEARCH_PROMPT.format(
            task_title=title,
            task_description=task_data.get("description", "No description"),
            acceptance_criteria=_format_acceptance_criteria(
                task_data.get("acceptance_criteria", [])
            ),
            constraints=_format_constraints(task_data),
            expected_outputs=_format_expected_outputs(
                task_data.get("expected_outputs", [])
            ),
            paper_context=paper_context,
            search_context=search_context,
            workspace_dir=self.workspace_dir,
        )

        # Execute with Claude (with research tools if enabled)
        result = await execute_task_with_claude(
            project_dir=self.project_dir,
            prompt=prompt,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
            non_interactive=True,
            enable_thinking=False,
            stall_timeout=0,  # No file watching — this is a pure generation task
        )

        if not result.success:
            print(f"  ❌ Verification research failed for {task_id}: "
                  f"{result.error or 'unknown error'}")
            return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}

        # Parse the output
        tests = _parse_test_output(result.output)

        n_num = len(tests["numerical_tests"])
        n_alg = len(tests["algorithmic_tests"])
        n_conv = len(tests["convergence_tests"])
        total = n_num + n_alg + n_conv

        print(f"  ✅ Generated {total} tests for {task_id}: "
              f"{n_num} numerical, {n_alg} algorithmic, {n_conv} convergence")

        return tests

    async def research_all_tasks(
        self,
        plan_data: dict,
        verification_level_filter: str = "scientific",
    ) -> dict:
        """Generate verification tests for all scientific tasks in a plan.

        Args:
            plan_data: Full plan dict from Phase 1
            verification_level_filter: Only research tasks with this level

        Returns:
            Dict mapping task_id → test results
        """
        tasks = plan_data.get("tasks", [])
        scientific_tasks = [
            t for t in tasks
            if t.get("verification_level", self._infer_verification_level(t))
            == verification_level_filter
        ]

        if not scientific_tasks:
            print("\n  ℹ️  No scientific tasks found — skipping verification research")
            return {}

        print(f"\n{'=' * 60}")
        print(f"  PHASE 1.5: VERIFY — Generating verification tests from papers")
        print(f"{'=' * 60}")
        print(f"  Scientific tasks: {len(scientific_tasks)}/{len(tasks)}")
        print(f"  References: {len(self.references)}")
        print(f"  Model: {self.model}")
        print(f"  Research enabled: {self.enable_research}")

        results = {}
        for task in scientific_tasks:
            task_id = task.get("id", "???")
            tests = await self.research_task(task)
            results[task_id] = tests

            # Merge tests back into plan_data
            task["numerical_tests"] = tests.get("numerical_tests", [])
            task["algorithmic_tests"] = tests.get("algorithmic_tests", [])
            task["convergence_tests"] = tests.get("convergence_tests", [])
            task["verification_level"] = "scientific"

        # Summary
        total_tests = sum(
            len(r.get("numerical_tests", [])) +
            len(r.get("algorithmic_tests", [])) +
            len(r.get("convergence_tests", []))
            for r in results.values()
        )
        print(f"\n  📊 Total: {total_tests} verification tests across "
              f"{len(scientific_tasks)} tasks")

        return results

    @staticmethod
    def _infer_verification_level(task_data: dict) -> str:
        """Infer verification level from task content if not explicitly set.

        Scientific keywords trigger scientific verification.
        """
        text = (
            task_data.get("title", "") + " " +
            task_data.get("description", "") + " " +
            " ".join(task_data.get("acceptance_criteria", []))
        ).lower()

        scientific_keywords = [
            "energy", "eigenvalue", "convergence", "hamiltonian",
            "variational", "ground state", "optimization", "tensor",
            "matrix product", "dmrg", "mps", "mpo", "svd",
            "numerical", "simulation", "benchmark", "scaling",
            "correctness", "accuracy", "tolerance", "precision",
            "algorithm", "contraction", "diagonalization",
        ]

        matches = sum(1 for kw in scientific_keywords if kw in text)
        return "scientific" if matches >= 3 else "standard"
