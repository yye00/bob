"""F-R7 PEAS pipeline entry-point: extract prose-only spec to features.yaml.

Wraps the full extract-from-peas pipeline (parse → stub → synthesize →
score-gate → write/print) behind a single callable function that satisfies
the AC for this feature.

Mirrors the run_pipeline() function in extract_from_peas.py but is exposed
as a top-level importable function with this module's canonical name so
the AC verifier can find it at:

    bob3.peas_pipeline_bob3_extract_peas_prose_only_spec_features
        .peas_pipeline_bob3_extract_peas_prose_only_spec_features
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.extract_from_peas import run_pipeline


def peas_pipeline_bob3_extract_peas_prose_only_spec_features(
    peas_path: Path,
    *,
    out_path: Path | None = None,
    threshold: float = 0.65,
    workspace: Path | None = None,
    existing_spec_path: Path | None = None,
    project_id: str = "extract-from-peas",
) -> dict[str, Any]:
    """Parse a PEAS prose-only markdown file and produce a features.yaml.

    Pipeline:
      1. Parse each ``## <title>`` section into a feature block.
      2. Emit a stub YAML feature per block (auto-mint F-R7-NNN when no Slot).
      3. Run the synthesizer to fill TBD acceptance criteria.
      4. Apply the spec-quality score gate.
      5. Write to *out_path* or capture as string; return a summary dict.

    Args:
        peas_path: Path to the input PEAS markdown file.
        out_path: Optional path to write the resulting features.yaml.
                  When absent the YAML is only returned in the summary dict.
        threshold: Minimum composite spec-quality score to pass the gate.
        workspace: Workspace root; defaults to cwd when None.
        existing_spec_path: Path to an existing features.yaml to avoid
                            slot collisions when auto-minting F-R7-NNN keys.
        project_id: Project identifier passed to the synthesizer.

    Raises:
        ValueError: When *peas_path* is not a Path (or path-like), does not
                    exist, or does not have a ``.md`` or ``.txt`` extension.

    Returns:
        Summary dict with keys:
          extracted     — number of feature sections parsed from the markdown
          synthesized   — number of features whose ACs were filled by the LLM
          gate_passed   — features whose score >= threshold
          gate_failed   — features whose score < threshold
          per_feature   — list of per-feature dicts (key, title, source, score)
          yaml_text     — the full YAML string ready to write to disk

    Boundary cases:
        Empty markdown (no ``## `` sections) → returns extracted=0, empty yaml.
        File not found → raises ValueError (wraps the underlying FileNotFoundError).
    """
    # Input validation — AC: raises ValueError for invalid input
    try:
        peas_path = Path(peas_path)
    except TypeError as exc:
        raise ValueError(f"peas_path must be a path-like object, got {type(peas_path).__name__}") from exc

    if not peas_path.exists():
        raise ValueError(f"PEAS file does not exist: {peas_path}")

    if peas_path.suffix.lower() not in (".md", ".txt", ""):
        raise ValueError(
            f"PEAS file must be a markdown (.md) or text (.txt) file, got: {peas_path.suffix!r}"
        )

    return run_pipeline(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=workspace,
        existing_spec_path=existing_spec_path,
        project_id=project_id,
    )
