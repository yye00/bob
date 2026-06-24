"""bob3.spec_findings_loader — safe loader for spec_findings.yaml.

Feature f3447fc6-0853-4e80-8bc6-5449036d8d1a

Safe boot-path loader that quarantines corrupt YAML and returns {} rather
than letting ScannerError crash bob3's boot sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_findings_writer import load_with_corruption_recovery

__all__ = ["load_spec_findings_safe", "load_with_corruption_handling"]


def load_spec_findings_safe(path: Path | str) -> dict[str, Any]:
    """Load spec_findings YAML safely, quarantining corruption instead of crashing.

    Delegates to load_with_corruption_recovery. On yaml.YAMLError the corrupt
    file is quarantined to <path>.corrupt.<unix_ts> and {} is returned so boot
    continues.

    Args:
        path: Path to the spec_findings YAML file.

    Returns:
        Parsed dict, or {} if the file is missing, empty, not a dict, or corrupt.
    """
    return load_with_corruption_recovery(path)


def load_with_corruption_handling(path: Path | str) -> dict[str, Any]:
    """AC-required alias for load_spec_findings_safe.

    On yaml.YAMLError (including ScannerError from partial writes), the corrupt
    file is quarantined to <path>.corrupt.<unix_ts> and {} is returned so bob3
    boot continues rather than crash-looping.

    Args:
        path: Path to the spec_findings YAML file.

    Returns:
        Parsed dict, or {} if the file is missing, empty, not a dict, or corrupt.
    """
    return load_with_corruption_recovery(path)
