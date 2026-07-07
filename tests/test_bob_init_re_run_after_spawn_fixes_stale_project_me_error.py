"""Error-path tests for bob.run_loop.verify_project_metadata.

Feature 1d00efac. Invalid input must raise ValueError; the function must not
silently succeed on a bad workspace argument type.
"""

from __future__ import annotations

import pytest

from bob.run_loop import verify_project_metadata


@pytest.mark.parametrize("bad_workspace", [123, 12.5, ["bob90"], {"w": "bob90"}, object()])
def test_invalid_workspace_type_raises_value_error(bad_workspace):
    """A non-path workspace type must raise ValueError, not silently succeed."""
    with pytest.raises(ValueError):
        verify_project_metadata(workspace=bad_workspace)


def test_invalid_workspace_type_error_names_the_type():
    """The ValueError message identifies the offending type so callers can debug."""
    with pytest.raises(ValueError, match="workspace must be"):
        verify_project_metadata(workspace=42)


def test_missing_database_raises(tmp_path):
    """A workspace whose bob.db does not exist surfaces an error rather than
    silently reporting success — sqlite cannot query a table in a fresh empty file."""
    workspace = tmp_path / "bob90"
    workspace.mkdir()
    missing_db = workspace / "does_not_exist.db"

    with pytest.raises(Exception):
        verify_project_metadata(workspace=workspace, db_path=missing_db)
