"""Sync check utilities for BOB.

This module provides utilities for checking if a project's spec source
has changed since the last sync, prompting users to sync before running.
"""

import hashlib
from datetime import datetime
from typing import Optional

from bob.database.manager import DatabaseManager
from bob.models.base import Project
from bob.spec_sources import get_registry


class SyncCheckResult:
    """Result of a sync check operation."""

    def __init__(
        self,
        sync_needed: bool,
        current_hash: Optional[str] = None,
        last_sync_hash: Optional[str] = None,
        last_sync_at: Optional[datetime] = None,
        reason: Optional[str] = None,
    ):
        self.sync_needed = sync_needed
        self.current_hash = current_hash
        self.last_sync_hash = last_sync_hash
        self.last_sync_at = last_sync_at
        self.reason = reason or "Spec source has not changed"

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.sync_needed


def compute_spec_source_hash(project: Project) -> str:
    """Compute hash of the spec source for a project.

    For file-based sources, this computes the SHA256 hash of the file contents.
    For other sources (GitHub, etc.), this may use API-based state or ETags.

    Args:
        project: Project to compute hash for

    Returns:
        Hex string hash of the spec source current state

    Raises:
        ValueError: If spec source cannot be accessed or hashed
    """
    # Get spec source from registry
    registry = get_registry()
    spec_source = registry.create(project.spec_source, project.config)

    # For file sources, we can compute the hash directly
    if hasattr(spec_source, '_compute_file_hash'):
        return spec_source._compute_file_hash()

    # For other sources, hash computation needs to be implemented
    # based on the specific source type (GitHub API, etc.)
    raise NotImplementedError(
        f"Hash computation not implemented for source type: {project.spec_source}. "
        f"Only file-based sources are currently supported."
    )


def check_sync_needed(project: Project) -> SyncCheckResult:
    """Check if a project needs to sync with its spec source.

    Compares the current spec source hash with the hash stored during
    the last sync. Returns a result indicating whether sync is needed.

    Args:
        project: Project to check

    Returns:
        SyncCheckResult with sync status and details

    Example:
        >>> result = check_sync_needed(project)
        >>> if result.sync_needed:
        ...     print(f"Sync needed: {result.reason}")
        ...     # Prompt user to run sync
    """
    # If project has never been synced, sync is needed
    if project.last_sync_hash is None:
        return SyncCheckResult(
            sync_needed=True,
            current_hash=None,
            last_sync_hash=None,
            last_sync_at=None,
            reason="Project has never been synced",
        )

    # Compute current hash of spec source
    try:
        current_hash = compute_spec_source_hash(project)
    except Exception as e:
        # If we can't compute the hash, be conservative and require sync
        return SyncCheckResult(
            sync_needed=True,
            current_hash=None,
            last_sync_hash=project.last_sync_hash,
            last_sync_at=project.last_sync_at,
            reason=f"Cannot compute spec source hash: {e}",
        )

    # Compare hashes
    if current_hash != project.last_sync_hash:
        return SyncCheckResult(
            sync_needed=True,
            current_hash=current_hash,
            last_sync_hash=project.last_sync_hash,
            last_sync_at=project.last_sync_at,
            reason="Spec source has changed since last sync",
        )

    # Spec is up to date
    return SyncCheckResult(
        sync_needed=False,
        current_hash=current_hash,
        last_sync_hash=project.last_sync_hash,
        last_sync_at=project.last_sync_at,
        reason="Spec source is up to date",
    )


def update_sync_hash(db: DatabaseManager, project: Project) -> None:
    """Update the project's last sync hash after a successful sync.

    This should be called after completing a successful sync operation
    to record the current state of the spec source.

    Args:
        db: DatabaseManager instance
        project: Project that was synced

    Example:
        >>> # After successful sync
        >>> update_sync_hash(db, project)
    """
    current_hash = compute_spec_source_hash(project)
    db.update_project(
        project_id=project.id,
        last_sync_hash=current_hash,
        last_sync_at=datetime.now(),
    )
