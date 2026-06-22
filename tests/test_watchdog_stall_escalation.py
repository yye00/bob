"""Tests for stall escalation in weekend_watchdog.sh.

AC-6: escalation fires at boundary (N-1 stalls silent; Nth stall produces sentinel + WARN log)
AC-7: STALL_ATTENTION.txt auto-cleared on Executing feature recovery
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

WATCHDOG_SH = Path(__file__).parent.parent / "tools" / "weekend_watchdog.sh"
assert WATCHDOG_SH.exists(), f"watchdog not found: {WATCHDOG_SH}"


def _run_watchdog_script(
    script: str,
    env: dict | None = None,
    tmpdir: Path | None = None,
) -> subprocess.CompletedProcess:
    """Source the watchdog and run an inline script against its functions."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    cmd = ["bash", "-c", f"source {WATCHDOG_SH} && {script}"]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(tmpdir) if tmpdir else str(WATCHDOG_SH.parent.parent),
        env=full_env,
    )


def _sentinel_path(home: Path, gen: int) -> Path:
    """Return the expected STALL_ATTENTION.txt path for a given gen.

    Mirrors the logic in _write_stall_attention:
      gen <= 4  → $HOME/dark-factory/bob/tools/STALL_ATTENTION.txt
      gen >  4  → $HOME/dark-factory/bob<gen-1>/tools/STALL_ATTENTION.txt
    """
    if gen <= 4:
        return home / "dark-factory" / "bob" / "tools" / "STALL_ATTENTION.txt"
    parent_gen = gen - 1
    return home / "dark-factory" / f"bob{parent_gen}" / "tools" / "STALL_ATTENTION.txt"


class TestStallEscalationThreshold:
    """AC-6: N-1 stalls are silent; Nth stall triggers sentinel + WARN log."""

    def test_default_threshold_is_5(self, tmp_path):
        result = _run_watchdog_script("_stall_escalation_count", tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "5"

    def test_env_override_respected(self, tmp_path):
        result = _run_watchdog_script(
            "_stall_escalation_count",
            env={"BOB3_STALL_ESCALATION_COUNT": "10"},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "10"

    def test_env_clamped_minimum_to_2(self, tmp_path):
        result = _run_watchdog_script(
            "_stall_escalation_count",
            env={"BOB3_STALL_ESCALATION_COUNT": "1"},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "2"

    def test_env_clamped_maximum_to_60(self, tmp_path):
        result = _run_watchdog_script(
            "_stall_escalation_count",
            env={"BOB3_STALL_ESCALATION_COUNT": "99"},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "60"

    def test_non_numeric_env_falls_back_to_default(self, tmp_path):
        result = _run_watchdog_script(
            "_stall_escalation_count",
            env={"BOB3_STALL_ESCALATION_COUNT": "banana"},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "5"

    def test_boundary_n_minus_1_no_sentinel(self, tmp_path):
        """N-1 stalls must NOT write the sentinel file (default threshold=5, so 4 stalls)."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            touch "$CHAIN_LOG"
            stall_count=0
            stall_first_observed=""
            for i in 1 2 3 4; do
                stall_count=$(( stall_count + 1 ))
                if [[ -z "$stall_first_observed" ]]; then
                    stall_first_observed="2026-01-01T00:00:00Z"
                fi
                stall_threshold=$(_stall_escalation_count)
                if [[ "$stall_count" -ge "$stall_threshold" ]]; then
                    _write_stall_attention 4 1 "$stall_count" "$stall_first_observed"
                fi
            done
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert not sentinel.exists(), \
            f"Sentinel written at N-1=4 stalls (threshold=5, too early): {sentinel}"

    def test_boundary_nth_stall_writes_sentinel(self, tmp_path):
        """Nth stall MUST write STALL_ATTENTION.txt (default threshold=5)."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            touch "$CHAIN_LOG"
            stall_count=0
            stall_first_observed=""
            for i in 1 2 3 4 5; do
                stall_count=$(( stall_count + 1 ))
                if [[ -z "$stall_first_observed" ]]; then
                    stall_first_observed="2026-01-01T00:00:00Z"
                fi
                stall_threshold=$(_stall_escalation_count)
                if [[ "$stall_count" -ge "$stall_threshold" ]]; then
                    _write_stall_attention 4 1 "$stall_count" "$stall_first_observed"
                fi
            done
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert sentinel.exists(), \
            f"STALL_ATTENTION.txt not written at Nth=5 stall. stderr: {result.stderr}"

    def test_nth_stall_sentinel_contains_required_fields(self, tmp_path):
        """Sentinel file must contain gen, round, observation_count, first_observed, and action hint."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            touch "$CHAIN_LOG"
            _write_stall_attention 4 2 7 "2026-05-28T20:39:00Z"
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert sentinel.exists(), "STALL_ATTENTION.txt not created"
        content = sentinel.read_text()
        assert "gen" in content and "4" in content
        assert "round" in content and "2" in content
        assert "observation_count" in content and "7" in content
        assert "2026-05-28T20:39:00Z" in content
        assert "drop" in content.lower() or "threshold" in content.lower(), \
            "Operator action hint (drop thresholds) missing"
        assert "relaunch" in content.lower(), "Operator action hint (relaunch) missing"

    def test_nth_stall_logs_chain_dead_locked_warn(self, tmp_path):
        """Escalation must log a WARN-level chain_dead_locked event to CHAIN_LOG."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            touch "$CHAIN_LOG"
            _write_stall_attention 4 1 5 "2026-01-01T00:00:00Z"
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert chain_log.exists()
        log_content = chain_log.read_text()
        assert "WARN" in log_content, "Expected WARN level in chain log"
        assert "chain_dead_locked" in log_content, \
            "Expected chain_dead_locked keyword in chain log"

    def test_warn_log_distinct_from_info_spec_gate_stall_observed(self, tmp_path):
        """chain_dead_locked WARN must be a distinct line from spec_gate_stall_observed INFO."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            touch "$CHAIN_LOG"
            log_info "spec_gate_stall_observed gen=4 consecutive=5 threshold=5 first_observed=2026-01-01T00:00:00Z"
            _write_stall_attention 4 1 5 "2026-01-01T00:00:00Z"
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        log_content = chain_log.read_text()
        lines = log_content.splitlines()

        info_lines = [l for l in lines if "INFO" in l and "spec_gate_stall_observed" in l]
        warn_lines = [l for l in lines if "WARN" in l and "chain_dead_locked" in l]
        assert info_lines, "No INFO spec_gate_stall_observed line found"
        assert warn_lines, "No WARN chain_dead_locked line found"
        assert info_lines[0] != warn_lines[0], \
            "INFO and WARN lines must be distinct"

    def test_custom_threshold_env_boundary(self, tmp_path):
        """With BOB3_STALL_ESCALATION_COUNT=3, sentinel appears at 3rd stall, not 5th."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"
        chain_log.write_text("")

        # 2 stalls (N-1 with threshold=3) — no sentinel
        script_no_sentinel = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            export BOB3_STALL_ESCALATION_COUNT=3
            stall_count=0; stall_first_observed=""
            for i in 1 2; do
                stall_count=$(( stall_count + 1 ))
                [[ -z "$stall_first_observed" ]] && stall_first_observed="2026-01-01T00:00:00Z"
                stall_threshold=$(_stall_escalation_count)
                if [[ "$stall_count" -ge "$stall_threshold" ]]; then
                    _write_stall_attention 4 1 "$stall_count" "$stall_first_observed"
                fi
            done
        """).strip()
        result = _run_watchdog_script(
            script_no_sentinel,
            env={"BOB3_STALL_ESCALATION_COUNT": "3"},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert not sentinel.exists(), \
            "Sentinel appeared before threshold=3 was reached (2 stalls is N-1)"

        # 3rd stall — sentinel must appear
        script_with_sentinel = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            export BOB3_STALL_ESCALATION_COUNT=3
            stall_count=2
            stall_first_observed="2026-01-01T00:00:00Z"
            stall_count=$(( stall_count + 1 ))
            stall_threshold=$(_stall_escalation_count)
            if [[ "$stall_count" -ge "$stall_threshold" ]]; then
                _write_stall_attention 4 1 "$stall_count" "$stall_first_observed"
            fi
        """).strip()
        result = _run_watchdog_script(
            script_with_sentinel,
            env={"BOB3_STALL_ESCALATION_COUNT": "3"},
            tmpdir=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert sentinel.exists(), \
            "Sentinel not written at Nth=3 stall with BOB3_STALL_ESCALATION_COUNT=3"


class TestStallAttentionAutoClear:
    """AC-7: STALL_ATTENTION.txt is automatically cleared on Executing feature recovery."""

    def test_clear_removes_sentinel_file(self, tmp_path):
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("stall sentinel content")
        chain_log = tmp_path / "chain.log"
        chain_log.write_text("")

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            _clear_stall_attention 4
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert not sentinel.exists(), "STALL_ATTENTION.txt was not removed on recovery"

    def test_clear_logs_recovery_message(self, tmp_path):
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("stall sentinel content")
        chain_log = tmp_path / "chain.log"
        chain_log.write_text("")

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            _clear_stall_attention 4
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        log_content = chain_log.read_text()
        assert "STALL_ATTENTION" in log_content or "cleared" in log_content.lower(), \
            f"Expected recovery log message, got: {log_content!r}"

    def test_clear_is_noop_when_no_sentinel(self, tmp_path):
        chain_log = tmp_path / "chain.log"
        chain_log.write_text("")

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            _clear_stall_attention 4
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, "clear should not fail when sentinel is absent"

    def test_stall_count_resets_after_clear(self, tmp_path):
        """After recovery, re-accumulating N-1 stalls does NOT re-escalate."""
        sentinel = _sentinel_path(tmp_path, gen=4)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("old stall")
        chain_log = tmp_path / "chain.log"
        chain_log.write_text("")

        # Clear sentinel, then run 4 new stall ticks (N-1 with default threshold=5).
        # The stall_count is reset to 0 after clear; 4 new ticks should not re-trigger.
        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            _clear_stall_attention 4
            stall_count=0; stall_first_observed=""
            for i in 1 2 3 4; do
                stall_count=$(( stall_count + 1 ))
                [[ -z "$stall_first_observed" ]] && stall_first_observed="2026-01-01T00:00:00Z"
                stall_threshold=$(_stall_escalation_count)
                if [[ "$stall_count" -ge "$stall_threshold" ]]; then
                    _write_stall_attention 4 1 "$stall_count" "$stall_first_observed"
                fi
            done
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert not sentinel.exists(), \
            "Sentinel re-appeared after clear with only N-1=4 new stall ticks"

    def test_sentinel_path_gen5_uses_bob4_tools(self, tmp_path):
        """For gen=5, sentinel must go to bob4/tools/ (parent gen)."""
        sentinel = _sentinel_path(tmp_path, gen=5)
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        chain_log = tmp_path / "chain.log"
        chain_log.write_text("")

        script = textwrap.dedent(f"""
            HOME="{tmp_path}"
            CHAIN_LOG="{chain_log}"
            STATE_FILE="{tmp_path}/state.json"
            touch "$CHAIN_LOG"
            _write_stall_attention 5 2 5 "2026-01-01T00:00:00Z"
        """).strip()
        result = _run_watchdog_script(script, tmpdir=tmp_path)
        assert result.returncode == 0, result.stderr
        assert sentinel.exists(), \
            f"STALL_ATTENTION.txt not at expected bob4/tools path: {sentinel}"
        assert "dark-factory/bob4/tools" in str(sentinel)


class TestWatchdogFileExists:
    """AC-0: tools/weekend_watchdog.sh must exist and be executable."""

    def test_file_exists(self):
        assert WATCHDOG_SH.exists(), f"weekend_watchdog.sh not found at {WATCHDOG_SH}"

    def test_file_is_executable(self):
        assert os.access(WATCHDOG_SH, os.X_OK), "weekend_watchdog.sh is not executable"

    def test_file_has_stall_escalation_functions(self):
        content = WATCHDOG_SH.read_text()
        assert "_stall_escalation_count" in content
        assert "_write_stall_attention" in content
        assert "_clear_stall_attention" in content

    def test_file_has_spec_gate_stall_observed_event(self):
        content = WATCHDOG_SH.read_text()
        assert "spec_gate_stall_observed" in content

    def test_file_has_chain_dead_locked_event(self):
        content = WATCHDOG_SH.read_text()
        assert "chain_dead_locked" in content

    def test_bob3_stall_escalation_count_env_referenced(self):
        content = WATCHDOG_SH.read_text()
        assert "BOB3_STALL_ESCALATION_COUNT" in content
