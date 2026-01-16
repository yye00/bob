"""Database migration management for BOB.

This module tracks schema versions and applies migrations.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Optional


# Current schema version
CURRENT_SCHEMA_VERSION = 2


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database.

    Args:
        conn: Database connection

    Returns:
        Current schema version (0 if not initialized)
    """
    try:
        cursor = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def initialize_schema_version(conn: sqlite3.Connection) -> None:
    """Initialize the schema version tracking table.

    Args:
        conn: Database connection
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description TEXT NOT NULL
        )
        """
    )
    conn.commit()


def apply_schema(conn: sqlite3.Connection, schema_path: Optional[Path] = None) -> None:
    """Apply the complete schema from schema.sql file.

    Args:
        conn: Database connection
        schema_path: Path to schema.sql file (defaults to package location)
    """
    if schema_path is None:
        # Default to the schema.sql in the same directory
        schema_path = Path(__file__).parent / "schema.sql"

    with open(schema_path, "r") as f:
        schema_sql = f.read()

    # Execute the entire schema
    conn.executescript(schema_sql)
    conn.commit()


def apply_migration_2(conn: sqlite3.Connection) -> None:
    """Add cache token tracking to sessions table.

    Args:
        conn: Database connection
    """
    # Add cache token columns to sessions table
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN tokens_cache_read INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass

    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN tokens_cache_write INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass

    conn.commit()


def migrate(conn: sqlite3.Connection, target_version: Optional[int] = None) -> None:
    """Apply database migrations.

    Args:
        conn: Database connection
        target_version: Target version to migrate to (defaults to latest)
    """
    if target_version is None:
        target_version = CURRENT_SCHEMA_VERSION

    # Initialize schema version tracking
    initialize_schema_version(conn)
    current_version = get_schema_version(conn)

    if current_version == 0:
        # Fresh database - apply full schema
        apply_schema(conn)
        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION, "Initial schema"),
        )
        conn.commit()
        print(f"✓ Applied schema version {CURRENT_SCHEMA_VERSION}", file=sys.stderr)
    elif current_version < target_version:
        # Apply migrations incrementally
        if current_version < 2:
            apply_migration_2(conn)
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (2, "Add cache token tracking to sessions"),
            )
            conn.commit()
            print(f"✓ Migrated to schema version 2", file=sys.stderr)
            current_version = 2

        if current_version < target_version:
            print(f"✓ Database now at version {current_version}", file=sys.stderr)
    else:
        print(f"✓ Database already at version {current_version}", file=sys.stderr)


def verify_schema(conn: sqlite3.Connection) -> bool:
    """Verify that all required tables exist and have correct structure.

    Args:
        conn: Database connection

    Returns:
        True if schema is valid, False otherwise
    """
    required_tables = [
        "projects",
        "tasks",
        "sessions",
        "events",
        "research_sessions",
        "schema_version",
    ]

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}

    missing_tables = set(required_tables) - existing_tables
    if missing_tables:
        print(f"✗ Missing tables: {missing_tables}", file=sys.stderr)
        return False

    # Verify foreign key constraints are enabled
    cursor = conn.execute("PRAGMA foreign_keys")
    fk_enabled = cursor.fetchone()[0]
    if not fk_enabled:
        print("✗ Foreign key constraints are not enabled", file=sys.stderr)
        return False

    return True
