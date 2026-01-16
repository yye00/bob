"""State management for BOB.

This module handles persistent state storage for BOB, including:
- Active project tracking
- User preferences
- Session state

State is stored in ~/.bob/state.json
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class StateManager:
    """Manages BOB's persistent state.

    State is stored in ~/.bob/state.json and includes:
    - active_project: Currently active project ID
    - last_updated: Timestamp of last state update
    - preferences: User preferences
    """

    def __init__(self, state_dir: Optional[Path] = None):
        """Initialize state manager.

        Args:
            state_dir: Directory for state files (defaults to ~/.bob)
        """
        if state_dir is None:
            state_dir = Path.home() / ".bob"

        self.state_dir = state_dir
        self.state_file = state_dir / "state.json"

        # Ensure state directory exists
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state file if it doesn't exist
        if not self.state_file.exists():
            self._write_state({
                "active_project": None,
                "last_updated": datetime.now().isoformat(),
                "preferences": {},
            })

    def _read_state(self) -> Dict[str, Any]:
        """Read state from file.

        Returns:
            State dictionary
        """
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Return default state if file doesn't exist or is invalid
            return {
                "active_project": None,
                "last_updated": datetime.now().isoformat(),
                "preferences": {},
            }

    def _write_state(self, state: Dict[str, Any]) -> None:
        """Write state to file atomically.

        Args:
            state: State dictionary to write
        """
        # Update timestamp
        state["last_updated"] = datetime.now().isoformat()

        # Write to temporary file first
        temp_file = self.state_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2)

        # Atomic rename
        temp_file.replace(self.state_file)

    def get_active_project(self) -> Optional[str]:
        """Get the currently active project ID.

        Returns:
            Project ID if set, None otherwise
        """
        state = self._read_state()
        return state.get("active_project")

    def set_active_project(self, project_id: str) -> None:
        """Set the active project.

        Args:
            project_id: Project ID to set as active
        """
        state = self._read_state()
        state["active_project"] = project_id
        self._write_state(state)

    def clear_active_project(self) -> None:
        """Clear the active project."""
        state = self._read_state()
        state["active_project"] = None
        self._write_state(state)

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference.

        Args:
            key: Preference key
            default: Default value if key not found

        Returns:
            Preference value or default
        """
        state = self._read_state()
        return state.get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference.

        Args:
            key: Preference key
            value: Preference value
        """
        state = self._read_state()
        if "preferences" not in state:
            state["preferences"] = {}
        state["preferences"][key] = value
        self._write_state(state)

    def get_all_state(self) -> Dict[str, Any]:
        """Get all state data.

        Returns:
            Complete state dictionary
        """
        return self._read_state()

    def clear_all_state(self) -> None:
        """Clear all state (reset to defaults)."""
        self._write_state({
            "active_project": None,
            "last_updated": datetime.now().isoformat(),
            "preferences": {},
        })
