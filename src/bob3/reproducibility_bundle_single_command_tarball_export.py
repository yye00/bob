"""Reproducibility bundle — single-command tarball export.

Public API for `bob3 bundle --run-id <id>`.

This module re-exports the core bundle functionality from bob3.bundle and
provides the CLI entry point. The bundle is a self-contained tarball
containing spec, transcript, diff, telemetry, and env lockfile so the
exact run can be inspected and reproduced offline.
"""

from bob3.bundle import create_bundle, _get_env_lockfile, _get_telemetry_lines

__all__ = ["create_bundle", "export_bundle"]


def export_bundle(run_id: str, output_dir=None, run_jsonl_path=None):
    """Export a reproducibility bundle for the given run_id.

    Thin wrapper around :func:`bob3.bundle.create_bundle` so callers can
    import from this module directly.

    Args:
        run_id: The sub_agent_run ID or feature ID to bundle.
        output_dir: Directory to write the tarball into. Defaults to cwd.
        run_jsonl_path: Path to run.jsonl for telemetry extraction.

    Returns:
        pathlib.Path to the created tarball.

    Raises:
        ValueError: If the run_id is not found in the database.
    """
    return create_bundle(
        run_id=run_id,
        output_dir=output_dir,
        run_jsonl_path=run_jsonl_path,
    )
