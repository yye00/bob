"""Tests for full sub-agent stderr/stdout capture (feature baf51448-8079-40ec-ad5a-eb46b571f36a).

Verifies:
- _attach_stderr_capture allocates a file-backed buffer and wires debug_stderr + extra_args
- captured_stderr_log path surfaced in error messages on sub-agent failure
- captured_stderr_tail surfaced in error messages on sub-agent failure
- _extract_error_head finds the first error marker in captured stderr
- Integration: bob3.orchestrator.claude_executor exports all required symbols
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.orchestrator.claude_executor import (
    _attach_stderr_capture,
    _ERROR_MARKERS,
    _extract_error_head,
    _format_spawn_exception,
    _persist_failure_artifacts,
)
from claude_code_sdk import ClaudeCodeOptions


# ---------------------------------------------------------------------------
# _attach_stderr_capture
# ---------------------------------------------------------------------------


class TestAttachStderrCapture:
    """_attach_stderr_capture must return a ClaudeCodeOptions with
    debug_stderr wired to the provided buffer and extra_args containing
    debug-to-stderr."""

    def _make_file_buffer(self):
        """Return a real NamedTemporaryFile (file-backed, has .fileno())."""
        return tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", delete=False, suffix=".stderr"
        )

    def test_returns_claude_code_options(self):
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(None, buf)
            assert isinstance(result, ClaudeCodeOptions)
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_sets_debug_stderr_to_buffer(self):
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(None, buf)
            assert result.debug_stderr is buf
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_sets_debug_to_stderr_extra_arg(self):
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(None, buf)
            assert result.extra_args is not None
            assert "debug-to-stderr" in result.extra_args
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_preserves_original_options_fields(self):
        original = ClaudeCodeOptions(
            model="claude-sonnet-4-5-20250929",
            max_turns=10,
            permission_mode="bypassPermissions",
        )
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(original, buf)
            assert result.model == original.model
            assert result.max_turns == original.max_turns
            assert result.permission_mode == original.permission_mode
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_does_not_mutate_original_options(self):
        original = ClaudeCodeOptions(max_turns=5)
        original_extra = dict(original.extra_args) if original.extra_args else {}
        buf = self._make_file_buffer()
        try:
            _attach_stderr_capture(original, buf)
            # Original extra_args must be unchanged
            after_extra = dict(original.extra_args) if original.extra_args else {}
            assert after_extra == original_extra
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_none_options_returns_valid_object(self):
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(None, buf)
            assert result is not None
            assert isinstance(result, ClaudeCodeOptions)
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_merges_caller_extra_args(self):
        original = ClaudeCodeOptions(extra_args={"my-flag": "value"})
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(original, buf)
            assert "my-flag" in result.extra_args
            assert "debug-to-stderr" in result.extra_args
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_buffer_must_be_file_backed(self):
        """NamedTemporaryFile has a real fd, unlike io.StringIO."""
        buf = self._make_file_buffer()
        try:
            # Must not raise — real file-backed buffer has .fileno()
            fd = buf.fileno()
            assert isinstance(fd, int)
        finally:
            buf.close()
            os.unlink(buf.name)

    def test_io_stringio_has_no_fileno(self):
        """Confirm io.StringIO lacks .fileno() — documents why we use NamedTemporaryFile."""
        sio = io.StringIO()
        with pytest.raises((io.UnsupportedOperation, AttributeError)):
            sio.fileno()


# ---------------------------------------------------------------------------
# _extract_error_head
# ---------------------------------------------------------------------------


class TestExtractErrorHead:
    """_extract_error_head must return text starting at the first error marker."""

    def test_returns_empty_for_empty_input(self):
        assert _extract_error_head("") == ""

    def test_returns_empty_when_no_marker_found(self):
        text = "Everything is fine. No problems here."
        assert _extract_error_head(text) == ""

    def test_finds_traceback_marker(self):
        text = "some preamble\nTraceback (most recent call last):\n  ...\nValueError: oops"
        head = _extract_error_head(text)
        assert "Traceback" in head

    def test_finds_error_colon_marker(self):
        text = "startup noise\nError: something went wrong\nmore noise"
        head = _extract_error_head(text)
        assert "Error: something went wrong" in head

    def test_finds_4xx_via_error_marker(self):
        text = "2024-01-01 INFO starting\nERROR: 400 BadRequest body\n2024-01-01 INFO stopping"
        head = _extract_error_head(text)
        assert "400 BadRequest" in head

    def test_respects_max_chars(self):
        long_traceback = "Traceback (most recent call last):\n" + "x" * 10000
        head = _extract_error_head(long_traceback, max_chars=100)
        assert len(head) <= 100

    def test_picks_earliest_marker(self):
        text = "preamble\nERROR: first error\nTraceback (most recent call last):\nlater"
        head = _extract_error_head(text)
        # Should start at "ERROR:" which appears first
        assert head.startswith("ERROR: first error")

    def test_all_markers_are_present_in_module(self):
        # Sanity: the markers tuple is exported and non-empty
        assert len(_ERROR_MARKERS) > 0
        for marker in _ERROR_MARKERS:
            assert isinstance(marker, str)


# ---------------------------------------------------------------------------
# _format_spawn_exception — captured_stderr_log and captured_stderr_tail
# ---------------------------------------------------------------------------


class TestFormatSpawnException:
    """_format_spawn_exception must include captured_stderr_log and captured_stderr_tail."""

    def _make_exc(self, msg="fail", exit_code=1):
        exc = RuntimeError(msg)
        exc.exit_code = exit_code  # type: ignore[attr-defined]
        return exc

    def test_includes_captured_stderr_log_when_log_path_provided(self):
        exc = self._make_exc()
        msg = _format_spawn_exception(exc, "some stderr", log_path=Path("/tmp/test.log"))
        assert "captured_stderr_log=" in msg

    def test_includes_captured_stderr_tail_when_stderr_provided(self):
        exc = self._make_exc()
        long_stderr = "a" * 2000
        msg = _format_spawn_exception(exc, long_stderr)
        assert "captured_stderr_tail=" in msg

    def test_log_path_value_in_message(self):
        exc = self._make_exc()
        log_path = Path("/tmp/agent_logs/test.stderr.log")
        msg = _format_spawn_exception(exc, "some stderr", log_path=log_path)
        assert str(log_path) in msg

    def test_tail_is_bounded_by_max_stderr_chars(self):
        exc = self._make_exc()
        long_stderr = "b" * 5000
        msg = _format_spawn_exception(exc, long_stderr, max_stderr_chars=100)
        # The tail section must not exceed 100 chars from the stderr
        tail_idx = msg.find("captured_stderr_tail=\n")
        assert tail_idx >= 0
        tail_content = msg[tail_idx + len("captured_stderr_tail=\n"):]
        assert len(tail_content) <= 100

    def test_no_log_path_still_includes_tail(self):
        exc = self._make_exc()
        msg = _format_spawn_exception(exc, "some captured output", log_path=None)
        assert "captured_stderr_tail=" in msg

    def test_empty_stderr_omits_tail(self):
        exc = self._make_exc()
        msg = _format_spawn_exception(exc, "")
        assert "captured_stderr_tail=" not in msg

    def test_includes_exception_type(self):
        exc = RuntimeError("oh no")
        msg = _format_spawn_exception(exc, "")
        assert "RuntimeError" in msg

    def test_includes_error_head_when_marker_found(self):
        exc = self._make_exc()
        stderr_with_error = "noise\nERROR: the real problem\nmore noise"
        msg = _format_spawn_exception(exc, stderr_with_error)
        assert "captured_stderr_head=" in msg
        assert "the real problem" in msg


# ---------------------------------------------------------------------------
# _persist_failure_artifacts
# ---------------------------------------------------------------------------


class TestPersistFailureArtifacts:
    """_persist_failure_artifacts writes stderr to .bob3/agent_logs/ and returns path."""

    def test_returns_path_on_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _persist_failure_artifacts(
            agent_run_id="abc123",
            captured_stderr="some stderr output",
            response_text="",
        )
        assert result is not None
        assert result.exists()

    def test_log_file_is_under_agent_logs_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _persist_failure_artifacts(
            agent_run_id="abc123",
            captured_stderr="stderr content",
            response_text="",
        )
        assert result is not None
        assert ".bob3" in str(result)
        assert "agent_logs" in str(result)

    def test_log_file_contains_stderr_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _persist_failure_artifacts(
            agent_run_id="run1",
            captured_stderr="unique_sentinel_12345",
            response_text="",
        )
        assert result is not None
        assert "unique_sentinel_12345" in result.read_text()

    def test_log_file_has_stderr_log_extension(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _persist_failure_artifacts(
            agent_run_id="run1",
            captured_stderr="content",
            response_text="",
        )
        assert result is not None
        assert result.name.endswith(".stderr.log")

    def test_includes_purpose_in_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _persist_failure_artifacts(
            agent_run_id="run1",
            captured_stderr="content",
            response_text="",
            purpose="implement_feature",
        )
        assert result is not None
        assert "implement_feature" in result.name

    def test_also_writes_response_when_non_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _persist_failure_artifacts(
            agent_run_id="run1",
            captured_stderr="stderr here",
            response_text="response here",
        )
        log_dir = tmp_path / ".bob3" / "agent_logs"
        response_files = list(log_dir.glob("*.response.txt"))
        assert len(response_files) >= 1

    def test_returns_none_on_io_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("bob3.orchestrator.claude_executor.Path.mkdir", side_effect=OSError("disk full")):
            result = _persist_failure_artifacts(
                agent_run_id="run1",
                captured_stderr="content",
                response_text="",
            )
        # Must return None, not raise
        assert result is None


# ---------------------------------------------------------------------------
# Integration: module exports
# ---------------------------------------------------------------------------


class TestModuleIntegration:
    """Integration check: bob3.orchestrator.claude_executor exports required symbols."""

    def test_attach_stderr_capture_is_callable(self):
        assert callable(_attach_stderr_capture)

    def test_extract_error_head_is_callable(self):
        assert callable(_extract_error_head)

    def test_format_spawn_exception_is_callable(self):
        assert callable(_format_spawn_exception)

    def test_persist_failure_artifacts_is_callable(self):
        assert callable(_persist_failure_artifacts)

    def test_module_has_captured_stderr_log_string(self):
        import bob3.orchestrator.claude_executor as mod
        src = Path(mod.__file__).read_text()
        assert "captured_stderr_log" in src

    def test_module_has_captured_stderr_tail_string(self):
        import bob3.orchestrator.claude_executor as mod
        src = Path(mod.__file__).read_text()
        assert "captured_stderr_tail" in src

    def test_attach_stderr_capture_signature(self):
        import inspect
        sig = inspect.signature(_attach_stderr_capture)
        params = list(sig.parameters.keys())
        assert "options" in params
        assert "buffer" in params
