"""Error path tests for Sub-agent startup-crash exempt from retry budget (F-R7-613).

These tests verify that invalid input raises ValueError and functions do not
silently succeed.

AC: pytest: tests/test_sub_agent_startup_crash_exempt_from_retry_budget_error.py
    — invalid input raises ValueError and the function does not silently succeed
      (error path)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.run_loop import load_exemption_sidecar


# ---------------------------------------------------------------------------
# load_exemption_sidecar error path tests
# ---------------------------------------------------------------------------


class TestLoadExemptionSidecarErrorPath:
    """Error path: invalid inputs must raise ValueError, not silently succeed."""

    def test_none_feature_id_raises_value_error(self, tmp_path: Path) -> None:
        """None feature_id must raise ValueError (not silently return 0 or a count)."""
        with pytest.raises(ValueError, match="feature_id must be a str"):
            load_exemption_sidecar(None, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_integer_feature_id_raises_value_error(self, tmp_path: Path) -> None:
        """Integer feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id must be a str"):
            load_exemption_sidecar(42, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_list_feature_id_raises_value_error(self, tmp_path: Path) -> None:
        """List feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id must be a str"):
            load_exemption_sidecar(["feat-id"], sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_dict_feature_id_raises_value_error(self, tmp_path: Path) -> None:
        """Dict feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id must be a str"):
            load_exemption_sidecar({"id": "feat"}, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]

    def test_none_feature_id_does_not_silently_return(self, tmp_path: Path) -> None:
        """Confirm None feature_id raises rather than returning any value."""
        raised = False
        try:
            result = load_exemption_sidecar(None, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]
        except ValueError:
            raised = True
        except Exception as exc:
            pytest.fail(f"Expected ValueError, got {type(exc).__name__}: {exc}")
        assert raised, "None feature_id must raise ValueError, not silently succeed"

    def test_corrupted_sidecar_content_returns_zero_not_raise(self, tmp_path: Path) -> None:
        """Corrupted (non-integer) sidecar content → returns 0, does not raise."""
        feature_id = "test-feature-corrupt"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("not-a-number")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 0

    def test_float_in_sidecar_returns_zero_not_raise(self, tmp_path: Path) -> None:
        """Float string in sidecar → treated as corrupted, returns 0."""
        feature_id = "test-feature-float"
        sidecar = tmp_path / f"{feature_id}.count"
        sidecar.write_text("3.14")
        result = load_exemption_sidecar(feature_id, sidecar_dir=str(tmp_path))
        assert result == 0

    def test_none_feature_id_error_message_is_descriptive(self, tmp_path: Path) -> None:
        """ValueError message must mention feature_id and the invalid type."""
        with pytest.raises(ValueError) as exc_info:
            load_exemption_sidecar(None, sidecar_dir=str(tmp_path))  # type: ignore[arg-type]
        error_text = str(exc_info.value)
        assert "feature_id" in error_text
        assert "str" in error_text


# ---------------------------------------------------------------------------
# Additional error path coverage for classify_subagent_startup_crash
# ---------------------------------------------------------------------------


class TestClassifySubagentStartupCrashErrorPath:
    """Error path coverage: classify_subagent_startup_crash behavior on bad inputs.

    The spec only requires ValueError for load_exemption_sidecar, but
    classify_subagent_startup_crash should never silently succeed with invalid
    types.
    """

    def test_string_exempt_counter_raises_or_returns_defined(self, tmp_path: Path) -> None:
        """String exempt_counter: must raise TypeError or return a well-defined dict."""
        from bob3.run_loop import classify_subagent_startup_crash
        try:
            result = classify_subagent_startup_crash(
                exit_signature="self signed certificate in certificate chain",
                workspace=str(tmp_path),
                exempt_counter="bad",  # type: ignore[arg-type]
            )
            assert isinstance(result, dict), "Must return a dict if not raising"
            assert result["decision"] in ("exempt", "charge", "cap_reached")
        except (TypeError, ValueError):
            pass  # explicit rejection is acceptable

    def test_negative_exempt_counter_is_handled_safely(self, tmp_path: Path) -> None:
        """Negative exempt_counter: never raises; returns well-defined result."""
        from bob3.run_loop import classify_subagent_startup_crash
        result = classify_subagent_startup_crash(
            exit_signature="self signed certificate in certificate chain",
            workspace=str(tmp_path),
            exempt_counter=-1,
        )
        assert isinstance(result, dict)
        assert result["decision"] in ("exempt", "charge", "cap_reached")
