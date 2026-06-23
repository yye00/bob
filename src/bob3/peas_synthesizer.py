"""PEAS synthesizer — canonical module for the extract-from-peas pipeline.

Exposes ``parse_peas_markdown``, ``synthesize_features``, and
``extract_from_peas`` as the AC-required functions at:
  bob3.peas_synthesizer.parse_peas_markdown
  bob3.peas_synthesizer.synthesize_features
  bob3.peas_synthesizer.extract_from_peas

Delegates to the full implementation in ``bob3.extract_from_peas``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.extract_from_peas import (
    parse_peas_markdown as _parse_peas_markdown,
    synthesize_features as _synthesize_features,
    emit_stub_features,
    extract_and_synthesize,
    run_pipeline,
    TBD_PLACEHOLDER,
)


def parse_peas_markdown(text: str) -> list[dict[str, Any]]:
    """Parse a PEAS markdown string into a list of feature dicts.

    Each ``## <title>`` heading starts a new feature block. The line
    immediately after the heading that contains ``Tier:``, ``Priority:``,
    or ``Slot:`` is parsed as metadata. All remaining lines in the block
    become the description.

    Returns a list of dicts with keys: ``title``, ``tier``, ``priority``,
    ``slot``, ``description``, ``permanent_forward_carry``.
    ``slot`` is ``None`` when absent.
    """
    return _parse_peas_markdown(text)


def synthesize_features(
    stubs: list[dict[str, Any]],
    *,
    project_id: str = "extract-from-peas",
    workspace: Path | None = None,
    _synthesize_fn: Any = None,
) -> list[dict[str, Any]]:
    """Run the synthesizer on a list of stub feature dicts to fill TBD ACs.

    Each stub must have at minimum ``key``, ``title``, and ``description``.
    When ``acceptance_criteria`` contains only the TBD placeholder, the
    synthesizer replaces it with real criteria; otherwise the stub is left
    unchanged.

    Returns the updated list of stubs (modified in-place and returned).
    *_synthesize_fn* is an optional async callable forwarded to the
    synthesizer; pass a fast local stub in tests.
    """
    return _synthesize_features(
        stubs,
        project_id=project_id,
        workspace=workspace,
        _synthesize_fn=_synthesize_fn,
    )


def extract_from_peas(
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

    Full extract-from-peas pipeline entry point:
      1. Parse each ``## <title>`` section into a feature block.
      2. Emit a YAML stub per block (auto-mint F-R7-NNN when Slot absent).
      3. Run the synthesizer to fill TBD acceptance criteria.
      4. Apply the spec-quality score gate.
      5. Write to *out_path* when given; always return a summary dict.

    Raises:
        ValueError: When *peas_path* does not exist or is not path-like.

    Returns:
        Summary dict with keys: extracted, synthesized, gate_passed,
        gate_failed, per_feature, yaml_text.
    """
    return extract_and_synthesize(
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
    "synthesize_features",
    "extract_from_peas",
    "emit_stub_features",
    "extract_and_synthesize",
    "run_pipeline",
    "TBD_PLACEHOLDER",
]
