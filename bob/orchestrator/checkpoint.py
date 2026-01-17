"""
CheckpointManager for BOB Framework
====================================

Manages session checkpointing to enable resuming interrupted sessions.

A checkpoint contains:
- Session metadata (ID, project, task)
- Conversation history (messages exchanged with Claude)
- Task state at checkpoint time
- Timestamp and checkpoint ID

Checkpoints are saved:
- Periodically during execution (every N turns)
- On graceful shutdown (Ctrl+C handler)
- On explicit request

Checkpoints enable:
- Resuming sessions after crashes or interruptions
- Reviewing conversation history
- Debugging session behavior
- Recovering from network failures
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bob.database.manager import DatabaseManager
from bob.models.base import Session, Task


class CheckpointManager:
    """
    Manages session checkpoints for resume capability.

    Checkpoints are stored in the project's .bob/checkpoints/ directory
    and contain conversation history and task state.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        workspace_dir: Path,
        checkpoint_interval: int = 5,
    ):
        """Initialize checkpoint manager.

        Args:
            db_manager: Database manager instance
            workspace_dir: Path to project workspace directory
            checkpoint_interval: Save checkpoint every N conversation turns
        """
        self.db_manager = db_manager
        self.workspace_dir = Path(workspace_dir)
        self.checkpoint_interval = checkpoint_interval

        # Create checkpoints directory
        self.checkpoint_dir = self.workspace_dir / ".bob" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        session_id: str,
        conversation_history: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Save a checkpoint for the current session.

        Args:
            session_id: ID of the session to checkpoint
            conversation_history: List of conversation messages
            metadata: Optional additional metadata to store

        Returns:
            Checkpoint ID (timestamp-based)
        """
        # Get session from database
        session = self.db_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Get current task if present
        task = None
        if session.task_id:
            task = self.db_manager.get_task(session.task_id)

        # Create checkpoint ID with microseconds for uniqueness
        timestamp = datetime.now(timezone.utc)
        checkpoint_id = f"{session_id}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"

        # Build checkpoint data
        checkpoint_data = {
            "checkpoint_id": checkpoint_id,
            "session_id": session_id,
            "project_id": session.project_id,
            "timestamp": timestamp.isoformat(),
            "session": {
                "id": session.id,
                "project_id": session.project_id,
                "task_id": session.task_id,
                "agent_type": session.agent_type.value if session.agent_type else None,
                "status": session.status.value if session.status else None,
                "model": session.model,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "turns": session.turns,
                "input_tokens": session.input_tokens,
                "output_tokens": session.output_tokens,
                "cache_read_tokens": session.cache_read_tokens,
                "cache_write_tokens": session.cache_write_tokens,
                "cost": session.cost,
            },
            "conversation_history": conversation_history,
            "turn_count": len(conversation_history),
        }

        # Add task state if present
        if task:
            checkpoint_data["task"] = {
                "id": task.id,
                "spec_id": task.spec_id,
                "title": task.title,
                "description": task.description,
                "status": task.status.value if task.status else None,
                "attempts": task.attempts,
                "escalation_tier": task.escalation_tier.value if task.escalation_tier else None,
                "current_model": task.current_model,
                "research_required": task.research_required,
                "research_complete": task.research_complete,
            }

        # Add metadata if provided
        if metadata:
            checkpoint_data["metadata"] = metadata

        # Save to file
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint_data, f, indent=2)

        return checkpoint_id

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore a checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint to restore

        Returns:
            Checkpoint data dictionary

        Raises:
            ValueError: If checkpoint not found
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_path.exists():
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        with open(checkpoint_path) as f:
            checkpoint_data = json.load(f)

        return checkpoint_data

    def list_checkpoints(
        self,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List available checkpoints.

        Args:
            session_id: Optional filter by session ID
            project_id: Optional filter by project ID
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoint metadata (sorted by timestamp, newest first)
        """
        checkpoints = []

        # Read all checkpoint files
        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file) as f:
                    data = json.load(f)

                # Apply filters
                if session_id and data.get("session_id") != session_id:
                    continue
                if project_id and data.get("project_id") != project_id:
                    continue

                # Extract metadata
                checkpoint_info = {
                    "checkpoint_id": data["checkpoint_id"],
                    "session_id": data["session_id"],
                    "project_id": data["project_id"],
                    "timestamp": data["timestamp"],
                    "turn_count": data["turn_count"],
                    "file_path": str(checkpoint_file),
                }

                # Add task info if present
                if "task" in data:
                    checkpoint_info["task_id"] = data["task"]["id"]
                    checkpoint_info["task_spec_id"] = data["task"]["spec_id"]
                    checkpoint_info["task_title"] = data["task"]["title"]

                checkpoints.append(checkpoint_info)
            except (json.JSONDecodeError, KeyError):
                # Skip invalid checkpoint files
                continue

        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda x: x["timestamp"], reverse=True)

        return checkpoints[:limit]

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint to delete

        Returns:
            True if deleted, False if not found
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if checkpoint_path.exists():
            checkpoint_path.unlink()
            return True

        return False

    def cleanup_old_checkpoints(
        self,
        session_id: Optional[str] = None,
        keep_last: int = 10,
    ) -> int:
        """Remove old checkpoints, keeping only the most recent.

        Args:
            session_id: Optional filter by session ID
            keep_last: Number of checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        # Get all checkpoints
        all_checkpoints = self.list_checkpoints(session_id=session_id, limit=1000)

        # Keep only the most recent
        to_delete = all_checkpoints[keep_last:]

        deleted_count = 0
        for checkpoint in to_delete:
            if self.delete_checkpoint(checkpoint["checkpoint_id"]):
                deleted_count += 1

        return deleted_count

    def should_save_checkpoint(self, turn_count: int) -> bool:
        """Determine if a checkpoint should be saved.

        Args:
            turn_count: Number of conversation turns so far

        Returns:
            True if checkpoint should be saved
        """
        # Save every N turns
        return turn_count > 0 and turn_count % self.checkpoint_interval == 0

    def get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """Get the file path for a checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint

        Returns:
            Path to checkpoint file
        """
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    def export_checkpoint(
        self,
        checkpoint_id: str,
        output_path: Path,
    ) -> None:
        """Export a checkpoint to a different location.

        Useful for archiving or sharing checkpoints.

        Args:
            checkpoint_id: ID of the checkpoint to export
            output_path: Path to export to
        """
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)

        if not checkpoint_path.exists():
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        shutil.copy2(checkpoint_path, output_path)

    def import_checkpoint(
        self,
        source_path: Path,
    ) -> str:
        """Import a checkpoint from a file.

        Args:
            source_path: Path to checkpoint file

        Returns:
            Checkpoint ID

        Raises:
            ValueError: If checkpoint file is invalid
        """
        # Read and validate checkpoint data
        with open(source_path) as f:
            checkpoint_data = json.load(f)

        # Validate required fields
        required_fields = ["checkpoint_id", "session_id", "project_id", "timestamp"]
        for field in required_fields:
            if field not in checkpoint_data:
                raise ValueError(f"Invalid checkpoint: missing field '{field}'")

        checkpoint_id = checkpoint_data["checkpoint_id"]

        # Copy to checkpoints directory
        checkpoint_path = self.get_checkpoint_path(checkpoint_id)
        shutil.copy2(source_path, checkpoint_path)

        return checkpoint_id
