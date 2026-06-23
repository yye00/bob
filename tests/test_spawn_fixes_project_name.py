"""Tests for AC: spawn_next_generation.sh calls bob3 init post-rsync.

Verifies that the spawn script includes the re-init step with --name and
--spec flags so that the child generation's projects table reflects the
correct generation metadata (name='bob{N+1}', spec_path pointing to the
real spec file) rather than the stale values copied via rsync.
"""
from __future__ import annotations

import re
from pathlib import Path


SPAWN_SCRIPT = Path(__file__).parents[1] / "tools" / "spawn_next_generation.sh"


def _script_text() -> str:
    return SPAWN_SCRIPT.read_text()


# ---------------------------------------------------------------------------
# Structural checks on spawn_next_generation.sh
# ---------------------------------------------------------------------------

def test_spawn_script_exists():
    assert SPAWN_SCRIPT.is_file(), f"Spawn script missing: {SPAWN_SCRIPT}"


def test_spawn_calls_bob_init_post_rsync():
    """Script must invoke bob3 init (via the gen-specific alias) after rsync."""
    text = _script_text()
    # The re-init block must appear *after* the rsync block.
    rsync_pos = text.find("rsync -a")
    assert rsync_pos != -1, "rsync block not found in spawn script"

    # Look for the pattern: .venv/bin/bob$NEXT_NUM init ...
    init_match = re.search(r'"\$NEXT_DIR/\.venv/bin/bob\$NEXT_NUM"\s+init', text)
    assert init_match is not None, (
        "spawn script does not call '$NEXT_DIR/.venv/bin/bob$NEXT_NUM init' after rsync"
    )
    assert init_match.start() > rsync_pos, (
        "bob{N+1} init call appears before rsync block"
    )


def test_spawn_passes_name_flag():
    """Re-init call must pass --name bob$NEXT_NUM."""
    text = _script_text()
    assert '--name "bob$NEXT_NUM"' in text or "--name bob$NEXT_NUM" in text, (
        "spawn script does not pass --name flag to bob init"
    )


def test_spawn_passes_spec_flag_for_next_gen():
    """Re-init call must pass --spec pointing to bootstrap_v0.$CURRENT_NUM.yaml."""
    text = _script_text()
    # The spec path must reference bootstrap_v0.$CURRENT_NUM
    assert "bootstrap_v0.$CURRENT_NUM.yaml" in text, (
        "spawn script does not reference bootstrap_v0.$CURRENT_NUM.yaml for --spec"
    )
    # And it must be passed as --spec
    assert "--spec" in text, "spawn script does not pass --spec to bob init"


def test_spawn_init_block_has_fallback_without_spec():
    """When spec file is absent, init is still called (without --spec)."""
    text = _script_text()
    # There should be a conditional: if spec file exists use --spec, else plain init
    assert 'if [[ -f "$SPEC_FOR_NEXT' in text or "if [ -f" in text or 'if [[ -f' in text, (
        "spawn script missing conditional for spec file presence"
    )
    # The else branch must still call bob$NEXT_NUM init
    # Verify there are at least 2 occurrences of 'init "$NEXT_DIR"' (or equivalent)
    init_calls = re.findall(
        r'"\$NEXT_DIR/\.venv/bin/bob\$NEXT_NUM"\s+init', text
    )
    assert len(init_calls) >= 2, (
        f"Expected at least 2 bob$NEXT_NUM init calls (spec / no-spec branches), "
        f"found {len(init_calls)}"
    )


def test_spawn_re_init_comment_explains_purpose():
    """A comment explaining WHY re-init is needed should be present."""
    text = _script_text()
    # Check for stale or metadata keywords in comments near re-init
    lower = text.lower()
    assert any(kw in lower for kw in ("stale", "metadata", "re-init", "reinit", "rsync copies")), (
        "spawn script missing explanatory comment for the re-init step"
    )
