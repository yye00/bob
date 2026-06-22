"""bob3.synthesizer.peas_extractor — PEAS pipeline adapter.

AC: File exists: src/bob3/synthesizer/peas_extractor.py
AC: Function defined: bob3.synthesizer.peas_extractor.parse_peas_markdown
AC: Function defined: bob3.synthesizer.peas_extractor.extract_to_features_yaml

Exposes the PEAS pipeline (parse → stub → synthesize → score-gate) as functions
in the bob3.synthesizer namespace.  Implementation delegates to
``bob3.extract_from_peas`` which owns the canonical logic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.extract_from_peas import (
    parse_peas_markdown as _parse_peas_markdown,
    extract_and_synthesize as _extract_and_synthesize,
    emit_stub_features,
    run_pipeline,
)


def parse_peas_markdown(text: str) -> list[dict[str, Any]]:
    """Parse a PEAS markdown string into a list of feature dicts.

    Each ``## <title>`` heading starts a new feature block. An optional
    metadata line with ``Tier:``, ``Priority:``, or ``Slot:`` keys is
    parsed; all remaining lines become the description.

    Returns:
        List of dicts with keys: ``title``, ``tier``, ``priority``,
        ``slot`` (None when absent), ``description``.
    """
    return _parse_peas_markdown(text)


def extract_to_features_yaml(
    peas_path: Path,
    *,
    out_path: Path | None = None,
    threshold: float = 0.65,
    workspace: Path | None = None,
    existing_spec_path: Path | None = None,
    project_id: str = "extract-from-peas",
    _synthesize_fn: Any = None,
) -> dict[str, Any]:
    """Parse a PEAS markdown file and synthesize acceptance criteria.

    Full pipeline:
      1. Parse each ``## <title>`` section into a feature block.
      2. Emit a stub YAML feature per block (auto-mint F-R7-NNN when Slot absent).
      3. Run the score-gate-loop synthesizer to fill TBD acceptance criteria.
      4. Write to *out_path* when given; always return a summary dict.
      5. Print summary: extracted=N, synthesized=N, gate_passed=N, gate_failed=N.

    Args:
        peas_path: Path to the input PEAS markdown file.
        out_path: Optional path to write the resulting features.yaml.
        threshold: Minimum composite spec-quality score for the gate.
        workspace: Workspace root; defaults to cwd when None.
        existing_spec_path: Existing features.yaml to avoid slot collisions.
        project_id: Project identifier passed to the synthesizer.
        _synthesize_fn: Optional async callable replacing the LLM call (tests).

    Raises:
        ValueError: When *peas_path* does not exist or is not path-like.

    Returns:
        Summary dict with keys: extracted, synthesized, gate_passed,
        gate_failed, per_feature, yaml_text.
    """
    return _extract_and_synthesize(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=workspace,
        existing_spec_path=existing_spec_path,
        project_id=project_id,
        _synthesize_fn=_synthesize_fn,
    )


__all__ = [
    "parse_peas_markdown",
    "extract_to_features_yaml",
    "emit_stub_features",
    "run_pipeline",
]
