"""Tests: spawn_next_generation.sh includes a 'bob init' invocation.

Asserts that tools/spawn_next_generation.sh contents include a 'bob init'
invocation after the rsync block, ensuring the child generation's DB is
re-initialized with correct project metadata after rsync.
"""
from __future__ import annotations

import re
from pathlib import Path

SPAWN_SCRIPT = Path(__file__).parents[1] / "tools" / "spawn_next_generation.sh"


def _script_text() -> str:
    return SPAWN_SCRIPT.read_text()


def test_spawn_script_file_exists():
    """tools/spawn_next_generation.sh must exist."""
    assert SPAWN_SCRIPT.is_file(), f"Script not found: {SPAWN_SCRIPT}"


def test_spawn_script_contains_bob_init():
    """Script must contain a 'bob init' string or equivalent alias invocation."""
    text = _script_text()
    # Either literal 'bob init' or the gen-specific alias pattern
    has_literal = "bob init" in text
    has_alias = bool(re.search(r'bob\$?NEXT_NUM"\s+init', text) or
                     re.search(r'bob\d+\s+init', text) or
                     re.search(r'/bin/bob[^"]*"\s+init', text))
    assert has_literal or has_alias, (
        "spawn_next_generation.sh does not contain a 'bob init' invocation"
    )


def test_spawn_script_init_after_rsync():
    """The init invocation must appear after the rsync block."""
    text = _script_text()
    rsync_pos = text.find("rsync")
    assert rsync_pos != -1, "No rsync call found in spawn script"

    # Find any init invocation
    init_match = re.search(r'init\s+.*--name', text)
    if init_match is None:
        # Try the alias pattern
        init_match = re.search(r'"\$NEXT_DIR/\.venv/bin/bob\$NEXT_NUM"\s+init', text)

    assert init_match is not None, "No 'init --name' call found in spawn script"
    assert init_match.start() > rsync_pos, (
        "init invocation appears before rsync block"
    )


def test_spawn_script_init_passes_name_flag():
    """The init invocation must pass --name."""
    text = _script_text()
    assert "--name" in text, "spawn script does not pass --name to init"


def test_spawn_script_init_references_next_generation():
    """The --name flag should reference the next generation number variable."""
    text = _script_text()
    # Should reference $NEXT_NUM or a numeric generation
    assert "NEXT_NUM" in text or re.search(r'--name\s+bob\d+', text), (
        "spawn script --name flag does not reference next generation"
    )
