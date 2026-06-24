"""bob.mutmut_verify_cli — CLI entry-point for the mutmut-verify command.

Usage
-----
    mutmut-verify --feature-id FEATURE_ID --src SRC_FILE [--src SRC_FILE ...] \\
                  --test-dir TEST_DIR [--workspace WORKSPACE] \\
                  [--threshold THRESHOLD] [--pytest-passed|--pytest-failed] \\
                  [--json-output]

Exit codes
----------
0  Gate passed (mutation_score >= threshold) or skipped (mutmut unavailable).
1  Gate rejected (mutation_score < threshold).
2  Input error.
"""

from __future__ import annotations

import json
import sys

import click

from bob.mutmut_verifier import verify_mutation_score


@click.command(name="mutmut-verify")
@click.option("--feature-id", required=True, help="Feature identifier.")
@click.option(
    "--src",
    "src_files",
    multiple=True,
    required=True,
    help="Source file(s) to mutate. Repeat for multiple files.",
)
@click.option("--test-dir", required=True, help="Test directory.")
@click.option("--workspace", default=".", show_default=True, help="Project workspace root.")
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Mutation score threshold (default 0.75).",
)
@click.option(
    "--pytest-passed/--pytest-failed",
    default=True,
    show_default=True,
    help="Whether pytest passed before calling the gate.",
)
@click.option("--json-output", is_flag=True, default=False, help="Print result as JSON.")
def main(
    feature_id: str,
    src_files: tuple[str, ...],
    test_dir: str,
    workspace: str,
    threshold: float | None,
    pytest_passed: bool,
    json_output: bool,
) -> None:
    """Verify mutation score for a feature implementation via mutmut.

    Mutates the source files and re-runs the test suite. Rejects the
    implementation if mutation_score < threshold (default 0.75). Surviving
    mutants are persisted to runs/<feature>/mutation_report.json for the
    next implementer attempt.
    """
    try:
        result = verify_mutation_score(
            feature_id=feature_id,
            src_files=list(src_files),
            test_dir=test_dir,
            workspace=workspace,
            pytest_passed=pytest_passed,
            threshold=threshold,
        )
    except (TypeError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if result is None:
        msg = "Gate skipped (pytest_passed=False or empty feature_id)."
        if json_output:
            click.echo(json.dumps({"skipped": True, "reason": msg}))
        else:
            click.echo(msg)
        sys.exit(0)

    if json_output:
        click.echo(json.dumps(result, indent=2))
    else:
        if result.get("skipped"):
            click.echo(f"Gate skipped: {result.get('reason', 'mutmut unavailable')}")
            sys.exit(0)

        score = result.get("mutation_score", 0.0)
        passed = result.get("passed", False)
        threshold_used = result.get("threshold", 0.75)

        click.echo(
            f"Mutation score: {score:.3f} | Threshold: {threshold_used} | "
            f"{'PASSED' if passed else 'REJECTED'}"
        )
        if not passed:
            click.echo(
                f"Feature {feature_id!r} rejected: mutation_score {score:.3f} "
                f"< {threshold_used}. See runs/{feature_id}/mutation_report.json."
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
