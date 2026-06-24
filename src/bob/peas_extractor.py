"""PEAS extractor — canonical entry-point for extract-from-peas pipeline.

Exposes ``extract_from_peas`` as the AC-required function at
``bob.peas_extractor.extract_from_peas``. Delegates to the full pipeline
in ``bob.extract_from_peas``.

AC: "File exists: src/bob/peas_extractor.py"
AC: "Function defined: bob.peas_extractor.extract_from_peas"
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.extract_from_peas import extract_and_synthesize


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
    """Parse a PEAS prose-only markdown file and synthesize acceptance criteria.

    Full pipeline:
      1. Parse each ``## <title>`` section into a feature block.
      2. Emit a stub YAML feature per block (auto-mint F-R7-NNN when no Slot).
      3. Run the synthesizer to fill TBD acceptance criteria.
      4. Apply the spec-quality score gate.
      5. Write to *out_path* when given; always return a summary dict.

    Args:
        peas_path: Path to the input PEAS markdown file.
        out_path: Optional path to write the resulting features.yaml.
        threshold: Minimum composite spec-quality score to pass the gate.
        workspace: Workspace root; defaults to cwd when None.
        existing_spec_path: Path to an existing features.yaml to avoid
                            slot collisions when auto-minting F-R7-NNN keys.
        project_id: Project identifier passed to the synthesizer.
        _synthesize_fn: Optional async callable replacing the default LLM
                        call; pass a fast stub in tests.

    Raises:
        ValueError: When *peas_path* does not exist or is not path-like.

    Returns:
        Summary dict with keys:
          extracted, synthesized, gate_passed, gate_failed,
          per_feature, yaml_text.
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
