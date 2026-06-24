"""Spec-to-test-plan generator (e30321ce-0115-43e6-887a-7777c8a3e748).

Generates a human-readable test plan from a feature spec before any sub-agent
is spawned. The test plan enumerates test scenarios, expected inputs/outputs,
edge cases, and maps each scenario to the acceptance criteria it covers.

The output is intended for:
  - Pre-run human review (spot-check before spawning)
  - Context injection into the plan-review agent

Public API::

    from bob.spec_to_test_plan_generator import (
        TestScenario,
        TestPlan,
        generate_test_plan,
        parse_acceptance_criteria,
        format_test_plan_markdown,
    )

    plan = generate_test_plan(feature)          # feature is a dict or Feature model
    md   = format_test_plan_markdown(plan)      # render to Markdown string
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TestScenario:
    """One test scenario within a TestPlan."""

    name: str
    description: str
    inputs: list[str]
    expected_outputs: list[str]
    edge_cases: list[str]
    covers_criteria: list[str]


@dataclass
class TestPlan:
    """Complete test plan for a single feature."""

    feature_name: str
    feature_description: str
    acceptance_criteria: list[str]
    scenarios: list[TestScenario]


# ---------------------------------------------------------------------------
# Acceptance-criteria parser
# ---------------------------------------------------------------------------

_AC_PREFIXES = ("File exists:", "pytest:", "Function defined:", "CLI command:", "python:")


def parse_acceptance_criteria(ac: Any) -> list[str]:
    """Normalise acceptance_criteria from any storage form into list[str]."""
    if ac is None:
        return []
    if isinstance(ac, list):
        return [str(x).strip() for x in ac if str(x).strip()]
    if isinstance(ac, str):
        s = ac.strip()
        if not s:
            return []
        # Try JSON array
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (json.JSONDecodeError, ValueError):
            pass
        # Plain single-criterion string
        return [s]
    return [str(ac).strip()]


# ---------------------------------------------------------------------------
# Scenario generation helpers
# ---------------------------------------------------------------------------

_PREFIX_LABELS = {
    "File exists:": "file",
    "pytest:": "pytest",
    "Function defined:": "function",
    "CLI command:": "cli",
    "python:": "python",
}


def _criterion_prefix(criterion: str) -> str:
    for prefix in _AC_PREFIXES:
        if criterion.startswith(prefix):
            return prefix
    return "other"


def _scenario_for_criterion(criterion: str, feature_name: str, feature_description: str) -> TestScenario:
    prefix = _criterion_prefix(criterion)
    value = criterion[len(prefix):].strip() if prefix != "other" else criterion

    if prefix == "File exists:":
        return TestScenario(
            name=f"File exists: {value}",
            description=f"Verify that the implementation creates the required file at `{value}`.",
            inputs=[f"Feature: {feature_name}"],
            expected_outputs=[f"`{value}` is present on disk after implementation"],
            edge_cases=[
                "File already exists from a prior run (idempotent write)",
                "Parent directory does not exist before implementation",
            ],
            covers_criteria=[criterion],
        )

    if prefix == "pytest:":
        return TestScenario(
            name=f"Tests pass: {value}",
            description=(
                f"Run `pytest {value}` and confirm all tests pass with meaningful assertions, "
                "no skips, and no stub implementations."
            ),
            inputs=[f"Feature: {feature_name}", f"Test file: {value}"],
            expected_outputs=[
                f"All tests in `{value}` pass",
                "No tests are skipped or xfailed unexpectedly",
                "No `assert True` placeholder assertions present",
            ],
            edge_cases=[
                "Test file does not yet exist before implementation starts",
                "Test file imports the module under test which may not exist yet",
            ],
            covers_criteria=[criterion],
        )

    if prefix == "Function defined:":
        return TestScenario(
            name=f"Function importable: {value}",
            description=(
                f"Verify that `{value}` is importable at runtime and resolves to a callable "
                "with real logic (not a stub)."
            ),
            inputs=[f"Feature: {feature_name}", f"Symbol: {value}"],
            expected_outputs=[
                f"`from {'.'.join(value.split('.')[:-1])} import {value.split('.')[-1]}` succeeds",
                f"`{value}` is a callable (function or method)",
            ],
            edge_cases=[
                "Module exists but function is missing",
                "Function is defined but raises NotImplementedError",
            ],
            covers_criteria=[criterion],
        )

    if prefix == "CLI command:":
        return TestScenario(
            name=f"CLI command works: {value}",
            description=f"Invoke `{value}` and verify it exits with code 0 and produces expected output.",
            inputs=[f"CLI invocation: {value}"],
            expected_outputs=["Exit code 0", "Expected stdout/stderr content"],
            edge_cases=[
                "Command invoked with --help flag",
                "Command invoked with invalid arguments",
            ],
            covers_criteria=[criterion],
        )

    if prefix == "python:":
        return TestScenario(
            name=f"Python expression true: {value}",
            description=f"Evaluate `{value}` and verify it returns a truthy result.",
            inputs=[f"Python expression: {value}"],
            expected_outputs=[f"`{value}` evaluates to True"],
            edge_cases=[
                "Expression raises an exception instead of returning False",
            ],
            covers_criteria=[criterion],
        )

    # Generic fallback for unknown criterion types
    return TestScenario(
        name=f"Criterion satisfied: {criterion}",
        description=f"Verify that the implementation satisfies: {criterion}",
        inputs=[f"Feature: {feature_name}"],
        expected_outputs=[f"Criterion is met: {criterion}"],
        edge_cases=[],
        covers_criteria=[criterion],
    )


def _happy_path_scenario(feature_name: str, feature_description: str) -> TestScenario:
    """A generic happy-path integration scenario when there are no specific criteria."""
    return TestScenario(
        name="Happy path: feature behaves as described",
        description=(
            f"Exercise the primary code path of '{feature_name}' with valid inputs "
            "and verify outputs match the feature description."
        ),
        inputs=["Valid inputs as described in the feature spec"],
        expected_outputs=["Feature produces expected outputs without errors"],
        edge_cases=[
            "Empty / zero-value inputs",
            "Large / boundary inputs",
            "Feature called multiple times (idempotency)",
        ],
        covers_criteria=[],
    )


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------


def generate_test_plan(feature: dict[str, Any]) -> TestPlan:
    """Generate a structured TestPlan from a feature dict.

    Args:
        feature: dict (or Feature model's __dict__) with at minimum
            ``name``, ``description``, and ``acceptance_criteria``.

    Returns:
        TestPlan with one TestScenario per acceptance criterion, plus
        edge-case coverage already embedded in each scenario.
    """
    name: str = feature.get("name") or "(unnamed feature)"
    description: str = feature.get("description") or ""
    ac_raw = feature.get("acceptance_criteria")

    criteria = parse_acceptance_criteria(ac_raw)

    if not criteria:
        scenarios: list[TestScenario] = [_happy_path_scenario(name, description)]
    else:
        scenarios = [_scenario_for_criterion(c, name, description) for c in criteria]

    return TestPlan(
        feature_name=name,
        feature_description=description,
        acceptance_criteria=criteria,
        scenarios=scenarios,
    )


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------


def format_test_plan_markdown(plan: TestPlan) -> str:
    """Render a TestPlan as a GitHub-flavoured Markdown document."""
    lines: list[str] = []

    lines.append(f"# Test Plan: {plan.feature_name}")
    lines.append("")

    lines.append("## Feature Overview")
    lines.append("")
    lines.append(f"**Name:** {plan.feature_name}")
    if plan.feature_description:
        lines.append(f"**Description:** {plan.feature_description}")
    lines.append("")

    if plan.acceptance_criteria:
        lines.append("## Acceptance Criteria")
        lines.append("")
        for i, criterion in enumerate(plan.acceptance_criteria, 1):
            lines.append(f"{i}. `{criterion}`")
        lines.append("")

    lines.append("## Test Scenarios")
    lines.append("")

    if not plan.scenarios:
        lines.append("_No scenarios generated._")
        lines.append("")
    else:
        for i, scenario in enumerate(plan.scenarios, 1):
            lines.append(f"### Scenario {i}: {scenario.name}")
            lines.append("")
            lines.append(f"**Description:** {scenario.description}")
            lines.append("")

            lines.append("**Inputs:**")
            for inp in scenario.inputs:
                lines.append(f"- {inp}")
            lines.append("")

            lines.append("**Expected Outputs:**")
            for out in scenario.expected_outputs:
                lines.append(f"- {out}")
            lines.append("")

            if scenario.edge_cases:
                lines.append("**Edge Cases:**")
                for ec in scenario.edge_cases:
                    lines.append(f"- {ec}")
                lines.append("")

            if scenario.covers_criteria:
                lines.append("**Covers Acceptance Criteria:**")
                for criterion in scenario.covers_criteria:
                    lines.append(f"- `{criterion}`")
                lines.append("")

    return "\n".join(lines)
