"""Tests for bob.version_probe — SDK version and model ID probing."""
import importlib.metadata
import os
import warnings
from unittest.mock import patch

import pytest

from bob.version_probe import get_model_id, get_sdk_version, preflight_version_check


class TestGetSdkVersion:
    def test_returns_string(self):
        result = get_sdk_version()
        assert isinstance(result, str)

    def test_returns_nonempty_string(self):
        result = get_sdk_version()
        assert result.strip() != ""

    def test_returns_unknown_when_package_not_found(self):
        with patch("importlib.metadata.version", side_effect=importlib.metadata.PackageNotFoundError):
            result = get_sdk_version()
        assert result == "unknown"

    def test_returns_installed_sdk_version(self):
        # Should return what importlib.metadata says for claude-code-sdk or anthropic
        result = get_sdk_version()
        # Must be a version-like string or "unknown"
        assert result == "unknown" or any(c.isdigit() for c in result)

    def test_uses_mock_version_when_patched(self):
        with patch("importlib.metadata.version", return_value="1.2.3"):
            result = get_sdk_version()
        assert result == "1.2.3"


class TestGetModelId:
    def test_returns_string(self):
        result = get_model_id()
        assert isinstance(result, str)

    def test_returns_nonempty_string(self):
        result = get_model_id()
        assert result.strip() != ""

    def test_respects_anthropic_default_sonnet_model_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_DEFAULT_SONNET_MODEL": "custom-model-xyz"}):
            result = get_model_id()
        assert result == "custom-model-xyz"

    def test_returns_default_model_when_no_env_var(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_DEFAULT_SONNET_MODEL"}
        with patch.dict(os.environ, env, clear=True):
            result = get_model_id()
        # Should return the canonical default sonnet model ID
        assert "claude" in result.lower() or "sonnet" in result.lower()

    def test_model_id_contains_version_hint(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_DEFAULT_SONNET_MODEL"}
        with patch.dict(os.environ, env, clear=True):
            result = get_model_id()
        # The model ID should contain digits (version numbers)
        assert any(c.isdigit() for c in result)


class TestPreflightVersionCheck:
    def test_no_warning_when_versions_match(self):
        with patch("bob.version_probe.get_sdk_version", return_value="0.0.25"):
            with patch("bob.version_probe._get_pinned_sdk_version", return_value="0.0.25"):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    preflight_version_check()
        sdk_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(sdk_warnings) == 0

    def test_emits_warning_when_versions_differ(self):
        with patch("bob.version_probe.get_sdk_version", return_value="1.0.0"):
            with patch("bob.version_probe._get_pinned_sdk_version", return_value="0.0.25"):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    preflight_version_check()
        sdk_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(sdk_warnings) == 1
        assert "1.0.0" in str(sdk_warnings[0].message)
        assert "0.0.25" in str(sdk_warnings[0].message)

    def test_no_warning_when_pinned_version_unavailable(self):
        with patch("bob.version_probe.get_sdk_version", return_value="0.0.25"):
            with patch("bob.version_probe._get_pinned_sdk_version", return_value=None):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    preflight_version_check()
        sdk_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(sdk_warnings) == 0

    def test_does_not_raise(self):
        # pre-flight check must never block execution
        with patch("bob.version_probe.get_sdk_version", return_value="99.0.0"):
            with patch("bob.version_probe._get_pinned_sdk_version", return_value="0.0.1"):
                preflight_version_check()  # must not raise


class TestTelemetryIntegration:
    def test_emit_telemetry_line_includes_sdk_version(self, tmp_path):
        import json
        from unittest.mock import patch as mpatch
        from bob.telemetry import emit_telemetry_line

        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        with mpatch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="probe-test")

        record = json.loads(run_jsonl.read_text())
        assert "sdk_version" in record
        assert isinstance(record["sdk_version"], str)

    def test_emit_telemetry_line_includes_model_id(self, tmp_path):
        import json
        from unittest.mock import patch as mpatch
        from bob.telemetry import emit_telemetry_line

        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        with mpatch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="probe-test")

        record = json.loads(run_jsonl.read_text())
        assert "model_id" in record
        assert isinstance(record["model_id"], str)

    def test_sdk_version_in_telemetry_matches_probe(self, tmp_path):
        import json
        from unittest.mock import patch as mpatch
        from bob.telemetry import emit_telemetry_line
        from bob.version_probe import get_sdk_version

        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        expected_version = get_sdk_version()
        with mpatch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="probe-version-match")

        record = json.loads(run_jsonl.read_text())
        assert record["sdk_version"] == expected_version

    def test_model_id_in_telemetry_matches_probe(self, tmp_path):
        import json
        from unittest.mock import patch as mpatch
        from bob.telemetry import emit_telemetry_line
        from bob.version_probe import get_model_id

        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        expected_model = get_model_id()
        with mpatch("bob.telemetry.get_run_jsonl_path", return_value=run_jsonl):
            emit_telemetry_line(run_id="probe-model-match")

        record = json.loads(run_jsonl.read_text())
        assert record["model_id"] == expected_model
