"""Tests for bob.state module (state management)."""

import json
from pathlib import Path

import pytest

from bob.state import StateManager


class TestStateManager:
    """Test StateManager class."""

    def test_init_creates_state_directory(self, tmp_path: Path) -> None:
        """Test that initialization creates state directory."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        assert state_dir.exists()
        assert state_dir.is_dir()

    def test_init_creates_state_file(self, tmp_path: Path) -> None:
        """Test that initialization creates state file."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        state_file = state_dir / "state.json"
        assert state_file.exists()
        assert state_file.is_file()

    def test_init_creates_default_state(self, tmp_path: Path) -> None:
        """Test that initialization creates default state."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        state_file = state_dir / "state.json"
        with open(state_file) as f:
            data = json.load(f)

        assert data["active_project"] is None
        assert "last_updated" in data
        assert data["preferences"] == {}

    def test_get_active_project_default(self, tmp_path: Path) -> None:
        """Test getting active project when none is set."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        assert state.get_active_project() is None

    def test_set_active_project(self, tmp_path: Path) -> None:
        """Test setting active project."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        project_id = "proj-12345678"
        state.set_active_project(project_id)

        assert state.get_active_project() == project_id

    def test_set_active_project_updates_file(self, tmp_path: Path) -> None:
        """Test that setting active project updates state file."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        project_id = "proj-12345678"
        state.set_active_project(project_id)

        # Read state file directly
        state_file = state_dir / "state.json"
        with open(state_file) as f:
            data = json.load(f)

        assert data["active_project"] == project_id

    def test_set_active_project_persists(self, tmp_path: Path) -> None:
        """Test that active project persists across StateManager instances."""
        state_dir = tmp_path / ".bob"

        # Create first instance and set active project
        state1 = StateManager(state_dir)
        project_id = "proj-12345678"
        state1.set_active_project(project_id)

        # Create second instance and verify active project
        state2 = StateManager(state_dir)
        assert state2.get_active_project() == project_id

    def test_clear_active_project(self, tmp_path: Path) -> None:
        """Test clearing active project."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        # Set and then clear
        state.set_active_project("proj-12345678")
        state.clear_active_project()

        assert state.get_active_project() is None

    def test_get_preference_default(self, tmp_path: Path) -> None:
        """Test getting preference with default value."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        assert state.get_preference("nonexistent", "default") == "default"
        assert state.get_preference("nonexistent") is None

    def test_set_preference(self, tmp_path: Path) -> None:
        """Test setting preference."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        state.set_preference("theme", "dark")
        assert state.get_preference("theme") == "dark"

    def test_set_multiple_preferences(self, tmp_path: Path) -> None:
        """Test setting multiple preferences."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        state.set_preference("theme", "dark")
        state.set_preference("editor", "vim")
        state.set_preference("auto_sync", True)

        assert state.get_preference("theme") == "dark"
        assert state.get_preference("editor") == "vim"
        assert state.get_preference("auto_sync") is True

    def test_preferences_persist(self, tmp_path: Path) -> None:
        """Test that preferences persist across StateManager instances."""
        state_dir = tmp_path / ".bob"

        # Create first instance and set preference
        state1 = StateManager(state_dir)
        state1.set_preference("theme", "dark")

        # Create second instance and verify preference
        state2 = StateManager(state_dir)
        assert state2.get_preference("theme") == "dark"

    def test_get_all_state(self, tmp_path: Path) -> None:
        """Test getting all state data."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        state.set_active_project("proj-12345678")
        state.set_preference("theme", "dark")

        all_state = state.get_all_state()

        assert all_state["active_project"] == "proj-12345678"
        assert all_state["preferences"]["theme"] == "dark"
        assert "last_updated" in all_state

    def test_clear_all_state(self, tmp_path: Path) -> None:
        """Test clearing all state."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        # Set some state
        state.set_active_project("proj-12345678")
        state.set_preference("theme", "dark")

        # Clear all state
        state.clear_all_state()

        # Verify everything is cleared
        assert state.get_active_project() is None
        assert state.get_preference("theme") is None
        all_state = state.get_all_state()
        assert all_state["preferences"] == {}

    def test_atomic_write(self, tmp_path: Path) -> None:
        """Test that state writes are atomic (use temp file + rename)."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        # Set active project
        state.set_active_project("proj-12345678")

        # Verify temp file doesn't exist after write
        temp_file = state_dir / "state.json.tmp"
        assert not temp_file.exists()

        # Verify state file exists and is valid JSON
        state_file = state_dir / "state.json"
        assert state_file.exists()
        with open(state_file) as f:
            data = json.load(f)
        assert data["active_project"] == "proj-12345678"

    def test_handles_corrupted_state_file(self, tmp_path: Path) -> None:
        """Test that StateManager handles corrupted state file gracefully."""
        state_dir = tmp_path / ".bob"
        state_dir.mkdir(parents=True, exist_ok=True)

        # Create corrupted state file
        state_file = state_dir / "state.json"
        with open(state_file, "w") as f:
            f.write("not valid json {{{")

        # Initialize StateManager (should handle corrupted file)
        state = StateManager(state_dir)

        # Should return default state
        assert state.get_active_project() is None
        assert state.get_preference("theme") is None

    def test_default_state_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that StateManager uses ~/.bob as default state directory."""
        # Mock home directory
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create StateManager without specifying state_dir
        state = StateManager()

        # Should create state in ~/.bob
        assert (tmp_path / ".bob").exists()
        assert (tmp_path / ".bob" / "state.json").exists()

    def test_updates_timestamp_on_write(self, tmp_path: Path) -> None:
        """Test that last_updated timestamp is updated on write."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        # Get initial timestamp
        initial_state = state.get_all_state()
        initial_timestamp = initial_state["last_updated"]

        # Wait a tiny bit and update state
        import time
        time.sleep(0.01)

        state.set_active_project("proj-12345678")

        # Get new timestamp
        new_state = state.get_all_state()
        new_timestamp = new_state["last_updated"]

        # Timestamp should be different
        assert new_timestamp != initial_timestamp

    def test_preference_types(self, tmp_path: Path) -> None:
        """Test that preferences can store different types."""
        state_dir = tmp_path / ".bob"
        state = StateManager(state_dir)

        # Store different types
        state.set_preference("string", "value")
        state.set_preference("number", 42)
        state.set_preference("float", 3.14)
        state.set_preference("boolean", True)
        state.set_preference("list", [1, 2, 3])
        state.set_preference("dict", {"key": "value"})

        # Verify all types are preserved
        assert state.get_preference("string") == "value"
        assert state.get_preference("number") == 42
        assert state.get_preference("float") == 3.14
        assert state.get_preference("boolean") is True
        assert state.get_preference("list") == [1, 2, 3]
        assert state.get_preference("dict") == {"key": "value"}
