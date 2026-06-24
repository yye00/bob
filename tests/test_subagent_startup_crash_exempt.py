"""Tests for Sub-agent startup-crash exempt from retry budget (F-R7-613).

Verifies the two required functions:
  - bob.run_loop.is_subagent_startup_crash
  - bob.run_loop.get_exempt_count

AC: pytest: tests/test_subagent_startup_crash_exempt.py
    integration: bob.run_loop
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.run_loop import get_exempt_count, is_subagent_startup_crash


# ---------------------------------------------------------------------------
# is_subagent_startup_crash tests
# ---------------------------------------------------------------------------


class TestIsSubagentStartupCrash:
    """Tests for is_subagent_startup_crash."""

    def test_returns_true_for_self_signed_certificate(self) -> None:
        """TLS self-signed cert error is a startup crash."""
        assert is_subagent_startup_crash("self signed certificate in certificate chain") is True

    def test_returns_true_for_connection_reset(self) -> None:
        """Connection reset error is a startup crash."""
        assert is_subagent_startup_crash("connection reset by peer") is True

    def test_returns_true_for_connection_reset_error(self) -> None:
        """ConnectionResetError string is a startup crash."""
        assert is_subagent_startup_crash("ConnectionResetError: [Errno 104] Connection reset by peer") is True

    def test_returns_true_for_read_timeout(self) -> None:
        """ReadTimeout is a startup crash."""
        assert is_subagent_startup_crash("ReadTimeout: HTTPSConnectionPool(host='github.com')") is True

    def test_returns_true_for_broken_pipe(self) -> None:
        """broken pipe is a startup crash."""
        assert is_subagent_startup_crash("BrokenPipeError: [Errno 32] Broken pipe") is True

    def test_returns_false_for_none(self) -> None:
        """None exit_signature is not a startup crash."""
        assert is_subagent_startup_crash(None) is False

    def test_returns_false_for_empty_string(self) -> None:
        """Empty string exit_signature is not a startup crash."""
        assert is_subagent_startup_crash("") is False

    def test_returns_false_for_normal_failure(self) -> None:
        """Normal test failure is not a startup crash."""
        assert is_subagent_startup_crash("AssertionError: assert 1 == 2") is False

    def test_returns_false_for_syntax_error(self) -> None:
        """SyntaxError is not a startup crash."""
        assert is_subagent_startup_crash("SyntaxError: invalid syntax") is False

    def test_returns_bool(self) -> None:
        """Return type must always be bool."""
        for sig in [None, "", "self signed certificate", "normal error"]:
            result = is_subagent_startup_crash(sig)
            assert isinstance(result, bool), f"Expected bool, got {type(result)} for sig={sig!r}"

    def test_mcp_server_connection_failed(self) -> None:
        """MCP server connection failure is a startup crash."""
        assert is_subagent_startup_crash("MCP server 'github' Connection failed: connection refused") is True

    def test_command_failed_exit_code_1(self) -> None:
        """Command failed with exit code 1 containing transport pattern is a startup crash."""
        assert is_subagent_startup_crash(
            "Command failed with exit code 1\nself signed certificate in certificate chain"
        ) is True


# ---------------------------------------------------------------------------
# get_exempt_count tests
# ---------------------------------------------------------------------------


class TestGetExemptCount:
    """Tests for get_exempt_count."""

    def test_returns_zero_for_unknown_feature(self, tmp_path: Path) -> None:
        """Feature with no sidecar returns 0."""
        result = get_exempt_count("unknown-feature-xyz", sidecar_dir=str(tmp_path))
        assert result == 0

    def test_returns_zero_for_empty_feature_id(self, tmp_path: Path) -> None:
        """Empty feature_id returns 0."""
        result = get_exempt_count("", sidecar_dir=str(tmp_path))
        assert result == 0

    def test_returns_count_from_sidecar(self, tmp_path: Path) -> None:
        """Returns the count stored in the sidecar file."""
        feature_id = "test-feature-abc123"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("3")
        result = get_exempt_count(feature_id, sidecar_dir=str(tmp_path))
        assert result == 3

    def test_returns_zero_for_nonexistent_dir(self) -> None:
        """Non-existent sidecar directory returns 0 (no raise)."""
        result = get_exempt_count("any-feature", sidecar_dir="/nonexistent/path/xyz999")
        assert result == 0

    def test_raises_value_error_for_none_feature_id(self, tmp_path: Path) -> None:
        """None feature_id raises ValueError."""
        with pytest.raises(ValueError):
            get_exempt_count(None, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_feature_id(self, tmp_path: Path) -> None:
        """Non-string feature_id raises ValueError."""
        with pytest.raises(ValueError):
            get_exempt_count(42, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_returns_int(self, tmp_path: Path) -> None:
        """Return type must always be int."""
        result = get_exempt_count("some-feature", sidecar_dir=str(tmp_path))
        assert isinstance(result, int)

    def test_corrupted_sidecar_returns_zero(self, tmp_path: Path) -> None:
        """Corrupted sidecar content returns 0, does not raise."""
        feature_id = "test-corrupt"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("not-a-number")
        result = get_exempt_count(feature_id, sidecar_dir=str(tmp_path))
        assert result == 0

    def test_env_var_used_when_no_explicit_dir(self, tmp_path: Path, monkeypatch) -> None:
        """BOB_STARTUP_EXEMPT_DIR env var used when sidecar_dir is None."""
        feature_id = "test-env-feature"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("5")
        monkeypatch.setenv("BOB_STARTUP_EXEMPT_DIR", str(tmp_path))
        result = get_exempt_count(feature_id, sidecar_dir=None)
        assert result == 5


# ---------------------------------------------------------------------------
# Integration: is_subagent_startup_crash feeds classify_subagent_startup_crash
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration: is_subagent_startup_crash is consistent with classify_subagent_startup_crash."""

    def test_transport_crash_is_exempt(self, tmp_path: Path) -> None:
        """Transport crash with no artifacts → exempt decision."""
        from bob.run_loop import classify_subagent_startup_crash

        exit_sig = "self signed certificate in certificate chain"
        assert is_subagent_startup_crash(exit_sig) is True

        result = classify_subagent_startup_crash(
            exit_signature=exit_sig,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "exempt"

    def test_non_transport_crash_is_charged(self, tmp_path: Path) -> None:
        """Non-transport crash → charge decision."""
        from bob.run_loop import classify_subagent_startup_crash

        exit_sig = "AssertionError: assert False"
        assert is_subagent_startup_crash(exit_sig) is False

        result = classify_subagent_startup_crash(
            exit_signature=exit_sig,
            workspace=str(tmp_path),
            exempt_counter=0,
        )
        assert result["decision"] == "charge"
