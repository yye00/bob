"""Pre-plan quality gates for the `bob plan` command.

Wires five spec-quality checks into the plan flow, all run BEFORE any
code is generated:

1. Schema validation (spec_quality.schema_constrained_emit): rejects specs
   that do not conform to schemas/spec.v1.json. Failure raises SpecSchemaError
   and is never silently retried.
2. Ambiguity linter (spec_quality.ambiguity_linter): rejects vague ACs.
3. Integration-target reachability (spec_quality.integration_reachability):
   rejects ``integration: <dotted.module>`` ACs whose target module is
   neither present in the workspace nor declared in the spec itself.
4. Composite spec_quality_score (tools.spec_quality_score): 8-sub-metric
   weighted geometric mean. Score < 0.65 blocks plan --create; 0.65–0.80
   warns; >= 0.80 silent green. Score persisted to specs/<feature>/quality.yaml.
5. Full 22-smell linter (bob.linter): Femmer/Smella + 2025 LLM-extension
   catalogue. E-severity findings block plan --create; W/I are surfaced only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from bob.orchestrator.spawn_retry import classify_exit, spawn_with_retry  # noqa: F401 — integration wiring
from bob.spec_quality.ambiguity_linter import lint_spec, SpecLintReport
from bob.spec_quality.integration_reachability import (
    check_spec as _check_reachability,
    ReachabilityResult,
)
from bob.spec_quality.schema_constrained_emit import (
    SpecSchemaError,
    validate_spec_dict,
)
from bob.linter import detect_smells, blocks_plan_create as _blocks_plan_create
from bob.plan import validate_plan_features  # noqa: F401 — AC-form validator wiring


def run_ac_form_gate(features: list[dict[str, Any]], console: Any) -> bool:
    """Run the AC-form validator gate over *features* before plan creation.

    Delegates to :func:`bob.plan.validate_plan_features`, which parses every
    acceptance criterion against the canonical grammar
    (pytest:/File exists:/Function defined:/Class defined:/integration:/behavior:)
    and refuses to persist any feature whose ACs are malformed — catching the
    v.13 parser-bug class at the source.

    Returns True when all ACs are well-formed, False otherwise. The caller is
    responsible for raising SystemExit(1) when this returns False.
    """
    try:
        validate_plan_features(features)
    except ValueError as exc:
        console.print(f"[red bold]AC-form validation FAILED:[/red bold]\n[red]{exc}[/red]")
        return False
    console.print(
        "[green]AC-form validation: PASSED[/green] "
        "(all acceptance criteria match the canonical grammar)"
    )
    return True


def run_schema_validation_gate(
    features: list[dict[str, Any]],
    console: Any,
    schema_path: Path | None = None,
) -> list[SpecSchemaError]:
    """Run schema validation on each feature spec in *features*.

    Each feature dict is validated against the pinned ``schemas/spec.v1.json``.
    Specs that fail are REJECTED with :class:`SpecSchemaError` — never silently
    coerced or retried. Returns a list of errors (empty on full pass).
    """
    errors: list[SpecSchemaError] = []
    for feature in features:
        feature_id = feature.get("id", "<unknown>")
        try:
            validate_spec_dict(feature, schema_path=schema_path, source_label=str(feature_id))
        except SpecSchemaError as exc:
            errors.append(exc)
            console.print(f"[red bold]Schema validation FAILED for {feature_id}:[/red bold]")
            console.print(f"[red]{exc}[/red]")

    if not errors:
        console.print(
            "[green]Schema validation: PASSED[/green] "
            "(all specs conform to schemas/spec.v1.json)"
        )
    return errors


def run_ambiguity_gate(features: list[dict[str, Any]], console: Any) -> SpecLintReport:
    """Run the ambiguity linter gate on *features*.

    Prints the lint report to *console*. Returns the report; the caller
    is responsible for failing the plan when ``report.passed`` is False.
    """
    report = lint_spec(features)
    if report.passed:
        console.print(
            "[green]Spec ambiguity lint: PASSED[/green] "
            "(all acceptance criteria are structured)"
        )
    else:
        console.print(f"[red bold]{report.format_report()}[/red bold]")
    return report


def run_integration_reachability_gate(
    features: list[dict[str, Any]],
    console: Any,
    workspace: Path | str | None = None,
) -> ReachabilityResult:
    """Run the integration-target reachability gate on *features*.

    For every ``integration: <dotted.module>`` AC, verifies the target
    module exists in the workspace or is declared in the spec. Prints
    the result to *console*. Returns the report; the caller is responsible
    for failing the plan when ``report.passed`` is False.
    """
    report = _check_reachability(features, workspace=workspace)
    if report.passed:
        console.print(
            "[green]Integration-target reachability: PASSED[/green] "
            "(all integration targets are reachable)"
        )
    else:
        console.print(f"[red bold]{report.format_report()}[/red bold]")
    return report


def run_composite_score_gate(
    features: list[dict[str, Any]],
    console: Any,
    workspace: Path | str | None = None,
) -> bool:
    """Run the composite spec_quality_score gate on each feature in *features*.

    Scores each feature using the 8-sub-metric weighted geometric mean from
    ``tools.spec_quality_score``. Persists each score to
    ``specs/<feature_slug>/quality.yaml`` relative to *workspace*.

    Gate bands:
      composite < 0.65  → blocks plan --create (returns False after printing all errors)
      0.65 ≤ composite < 0.80 → warns but proceeds
      composite ≥ 0.80 → silent green

    Returns True when all features pass (>= 0.65), False when any are blocked.
    The caller is responsible for raising SystemExit(1) when this returns False.
    """
    try:
        # tools/ is not a package — insert to sys.path relative to workspace
        ws = Path(workspace) if workspace is not None else Path.cwd()
        tools_dir = str(ws / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from spec_quality_score import compute, GATE_BLOCK, GATE_WARN  # type: ignore[import]
    except ImportError:
        console.print(
            "[yellow]spec_quality_score: tools/spec_quality_score.py not found "
            "— skipping composite gate[/yellow]"
        )
        return True

    try:
        import yaml as _yaml
    except ImportError:
        console.print("[yellow]spec_quality_score: pyyaml not available — skipping yaml persist[/yellow]")
        _yaml = None  # type: ignore[assignment]

    any_blocked = False

    for feature in features:
        name = feature.get("title") or feature.get("name") or "<unnamed>"
        description = feature.get("description") or None
        ac_raw = feature.get("acceptance_criteria") or []

        # Normalise JSON-encoded lists stored as strings in the feature dict
        if isinstance(ac_raw, str):
            stripped = ac_raw.strip()
            if stripped.startswith("["):
                try:
                    ac_raw = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    ac_raw = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
            else:
                ac_raw = [ln.strip() for ln in stripped.splitlines() if ln.strip()]

        result = compute(name=name, description=description, acceptance_criteria=ac_raw, workspace=ws)

        # Persist to specs/<feature_slug>/quality.yaml
        if _yaml is not None:
            slug = re.sub(r"[^a-z0-9_-]", "_", name.lower())[:64]
            quality_dir = ws / "specs" / slug
            try:
                quality_dir.mkdir(parents=True, exist_ok=True)
                quality_path = quality_dir / "quality.yaml"
                with open(quality_path, "w") as _f:
                    _yaml.dump(result.as_dict(), _f)
            except OSError:
                pass  # non-fatal — gate still enforced

        composite = result.composite
        if composite < GATE_BLOCK:
            rationale = "\n".join(result.rationale) if result.rationale else "Score below threshold"
            console.print(
                f"[red bold]spec_quality_score BLOCKED for '{name}':[/red bold] "
                f"composite={composite:.4f} < {GATE_BLOCK}\n"
                f"[red]Rationale:\n{rationale}[/red]"
            )
            any_blocked = True
        elif composite < GATE_WARN:
            console.print(
                f"[yellow]spec_quality_score WARNING for '{name}':[/yellow] "
                f"composite={composite:.4f} (between {GATE_BLOCK} and {GATE_WARN}). "
                "Proceeding, but spec quality is below the green threshold."
            )
        else:
            pass  # silent green

    if not any_blocked:
        console.print(
            "[green]Composite spec_quality_score: PASSED[/green] "
            "(all features score >= 0.65)"
        )

    return not any_blocked


def run_smell_linter_gate(
    features: list[dict[str, Any]],
    console: Any,
) -> bool:
    """Run the full 22-smell linter gate on each feature in *features*.

    For every acceptance criterion in each feature, runs the complete
    Femmer/Smella + 2025 LLM-extension 22-detector catalogue via
    ``bob.linter.detect_smells``.

    Gate behaviour:
      E-severity findings → block plan --create (returns False)
      W-severity findings → surfaced to console, does not block
      I-severity findings → surfaced to console, does not block

    Returns True when no feature has E-severity findings, False otherwise.
    The caller is responsible for raising SystemExit(1) when this returns False.
    """
    any_blocked = False

    for feature in features:
        feature_id = feature.get("id") or feature.get("name") or "<unknown>"
        ac_raw = feature.get("acceptance_criteria") or []

        if isinstance(ac_raw, str):
            stripped = ac_raw.strip()
            if stripped.startswith("["):
                try:
                    ac_raw = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    ac_raw = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
            else:
                ac_raw = [ln.strip() for ln in stripped.splitlines() if ln.strip()]

        peer_criteria = list(ac_raw)
        feature_blocked = False

        for ac_text in ac_raw:
            if not isinstance(ac_text, str):
                continue
            findings = detect_smells(
                ac_text,
                peer_criteria=peer_criteria,
            )
            for f in findings:
                if f.severity == "E":
                    console.print(
                        f"[red bold]Smell linter BLOCKED [{feature_id}] AC '{ac_text[:60]}...' "
                        f"→ {f.smell_id} ({f.smell_name}): {f.detail}[/red bold]"
                    )
                    feature_blocked = True
                elif f.severity == "W":
                    console.print(
                        f"[yellow]Smell linter WARNING [{feature_id}]: "
                        f"{f.smell_id} ({f.smell_name}): {f.detail}[/yellow]"
                    )
                else:
                    console.print(
                        f"[dim]Smell linter INFO [{feature_id}]: "
                        f"{f.smell_id} ({f.smell_name}): {f.detail}[/dim]"
                    )

        if feature_blocked:
            any_blocked = True

    if not any_blocked:
        console.print(
            "[green]22-smell linter: PASSED[/green] "
            "(no E-severity findings — plan --create not blocked)"
        )

    return not any_blocked
