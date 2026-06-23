"""Spec versioning and diff tracking for bob3.

Provides:
- version_spec(spec_dict) -> str  — SHA-256 of canonical YAML
- diff_specs(old, new) -> SpecDiff — keys added/removed/modified
- watch_spec_file(spec_path, run_id, on_change) — emit spec_version_changed
- check_spec_change_abort(old_version, new_version) — abort if env says so
- SpecChangedAbort — exception raised when BOB3_ABORT_ON_SPEC_CHANGE=true
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

# ---------------------------------------------------------------------------
# version_spec
# ---------------------------------------------------------------------------

_STATE: dict[str, str] = {}  # spec_path str -> last seen version hash


def version_spec(spec_dict: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of the canonical YAML of *spec_dict*.

    Canonical form: yaml.dump with sort_keys=True so key insertion order
    does not affect the hash.
    """
    canonical = yaml.dump(spec_dict, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# SpecDiff
# ---------------------------------------------------------------------------


@dataclass
class SpecDiff:
    """Result of comparing two spec dicts.

    added:    top-level keys present in new but not old
    removed:  top-level keys present in old but not new
    modified: top-level keys present in both but with different values
    """

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# diff_specs
# ---------------------------------------------------------------------------


def diff_specs(old: dict[str, Any], new: dict[str, Any]) -> SpecDiff:
    """Compare two spec dicts and return a SpecDiff of top-level key changes."""
    old_keys = set(old.keys())
    new_keys = set(new.keys())

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(k for k in old_keys & new_keys if old[k] != new[k])

    return SpecDiff(added=added, removed=removed, modified=modified)


# ---------------------------------------------------------------------------
# watch_spec_file
# ---------------------------------------------------------------------------


def watch_spec_file(
    *,
    spec_path: Path,
    run_id: str,
    on_change: Callable[[dict[str, Any]], None],
) -> None:
    """Compare the current spec file hash to the last known hash for this path.

    On the first call for a given *spec_path*, records the current hash and
    calls *on_change* only if the file has changed since the previous call.

    Args:
        spec_path: Path to the YAML spec file.
        run_id:    Identifier for the current run (included in the event).
        on_change: Callback invoked with an event dict when a change is detected.
                   Event keys: event, run_id, old_version, new_version.
    """
    spec_path = Path(spec_path)
    raw = yaml.safe_load(spec_path.read_text()) or {}
    current_version = version_spec(raw)

    key = str(spec_path.resolve())
    previous_version = _STATE.get(key)

    if previous_version is None:
        # First observation — record baseline, no change event
        _STATE[key] = current_version
        return

    if current_version == previous_version:
        return

    _STATE[key] = current_version
    on_change({
        "event": "spec_version_changed",
        "run_id": run_id,
        "old_version": previous_version,
        "new_version": current_version,
    })


# ---------------------------------------------------------------------------
# SpecChangedAbort + check_spec_change_abort
# ---------------------------------------------------------------------------


class SpecChangedAbort(Exception):
    """Raised when the spec changes mid-run and BOB3_ABORT_ON_SPEC_CHANGE is true."""


def _abort_on_spec_change() -> bool:
    """Return True if BOB3_ABORT_ON_SPEC_CHANGE is enabled (default: True)."""
    val = os.environ.get("BOB3_ABORT_ON_SPEC_CHANGE", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


def check_spec_change_abort(*, old_version: str, new_version: str) -> None:
    """Raise SpecChangedAbort if the spec changed and abort mode is enabled.

    If old_version == new_version this is a no-op regardless of the env var.
    """
    if old_version == new_version:
        return
    if _abort_on_spec_change():
        raise SpecChangedAbort(
            f"Spec changed mid-run: {old_version!r} -> {new_version!r}. "
            "Set BOB3_ABORT_ON_SPEC_CHANGE=false to continue anyway."
        )
