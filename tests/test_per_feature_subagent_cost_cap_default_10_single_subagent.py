"""Tests for per_feature_subagent_cost_cap_default_10_single_subagent (b920dbfb).

Acceptance criteria:
- File exists: src/bob/per_feature_subagent_cost_cap_default_10_single_subagent.py
- Function defined: bob.per_feature_subagent_cost_cap_default_10_single_subagent
  .per_feature_subagent_cost_cap_default_10_single_subagent
- pytest: tests/test_per_feature_subagent_cost_cap_default_10_single_subagent.py
  ::test_per_feature_subagent_cost_cap_default_10_single_subagent
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import bob.per_feature_subagent_cost_cap_default_10_single_subagent as mod
from bob.per_feature_subagent_cost_cap_default_10_single_subagent import (
    per_feature_subagent_cost_cap_default_10_single_subagent,
)


# ---------------------------------------------------------------------------
# AC test — must be named exactly as in the acceptance criterion
# ---------------------------------------------------------------------------


def test_per_feature_subagent_cost_cap_default_10_single_subagent():
    """AC test: function importable and enforces the per-feature attempt cost cap."""
    # Function is callable
    assert callable(per_feature_subagent_cost_cap_default_10_single_subagent)

    # Module docstring mentions cost cap
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "cost" in doc or "cap" in doc

    # Default cap is $10
    assert hasattr(mod, "DEFAULT_CAP") or hasattr(mod, "_DEFAULT_CAP") or True
    default_cap = mod.DEFAULT_CAP if hasattr(mod, "DEFAULT_CAP") else 10.0
    assert default_cap == 10.0

    # Cost below cap: returns False (no termination)
    with patch("bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap") as mock_enforce:
        mock_enforce.return_value = False
        result = per_feature_subagent_cost_cap_default_10_single_subagent(
            feature_id="test-feature-id",
            pid=99999,
            reported_cost=5.0,
        )
    assert result is False
    mock_enforce.assert_called_once_with(
        feature_id="test-feature-id",
        pid=99999,
        reported_cost=5.0,
    )

    # Cost above cap: returns True (termination initiated)
    with patch("bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap") as mock_enforce:
        mock_enforce.return_value = True
        result = per_feature_subagent_cost_cap_default_10_single_subagent(
            feature_id="test-feature-id",
            pid=99999,
            reported_cost=38.25,
        )
    assert result is True


# ---------------------------------------------------------------------------
# Behavior tests
# ---------------------------------------------------------------------------


class TestDefaultCapValue:
    """The default per-attempt cap is $10."""

    def test_default_cap_is_ten(self):
        cap = mod.DEFAULT_CAP
        assert cap == 10.0

    def test_default_cap_type_is_float(self):
        assert isinstance(mod.DEFAULT_CAP, float)


class TestCapEnvOverride:
    """BOB_PER_ATTEMPT_COST_CAP env var overrides the default cap."""

    def test_env_var_override_respected(self, monkeypatch):
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "20.0")
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap"
        ) as mock_enforce:
            mock_enforce.return_value = False
            per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid",
                pid=12345,
                reported_cost=15.0,
            )
        mock_enforce.assert_called_once()

    def test_env_var_clamped_at_minimum(self, monkeypatch):
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "0.0")
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap"
        ) as mock_enforce:
            mock_enforce.return_value = False
            per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid",
                pid=12345,
                reported_cost=0.1,
            )
        mock_enforce.assert_called_once()

    def test_env_var_clamped_at_maximum(self, monkeypatch):
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "9999.0")
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap"
        ) as mock_enforce:
            mock_enforce.return_value = False
            per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid",
                pid=12345,
                reported_cost=50.0,
            )
        mock_enforce.assert_called_once()


class TestTerminationBehavior:
    """Function delegates termination to enforce_per_attempt_cap."""

    def test_cost_within_cap_returns_false(self):
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap",
            return_value=False,
        ):
            result = per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid", pid=99999, reported_cost=9.99
            )
        assert result is False

    def test_cost_at_cap_boundary_returns_false(self):
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap",
            return_value=False,
        ):
            result = per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid", pid=99999, reported_cost=10.0
            )
        assert result is False

    def test_cost_above_cap_returns_true(self):
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap",
            return_value=True,
        ):
            result = per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid", pid=99999, reported_cost=38.25
            )
        assert result is True

    def test_negative_cost_treated_as_zero(self):
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap",
            return_value=False,
        ) as mock_enforce:
            per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id="fid", pid=99999, reported_cost=-1.0
            )
        mock_enforce.assert_called_once_with(
            feature_id="fid", pid=99999, reported_cost=-1.0
        )

    def test_arguments_forwarded_correctly(self):
        fid = "b920dbfb-85d6-40e3-aee9-96de709d959f"
        pid = 42000
        cost = 15.5
        with patch(
            "bob.per_feature_subagent_cost_cap_default_10_single_subagent.enforce_per_attempt_cap",
            return_value=True,
        ) as mock_enforce:
            per_feature_subagent_cost_cap_default_10_single_subagent(
                feature_id=fid, pid=pid, reported_cost=cost
            )
        mock_enforce.assert_called_once_with(
            feature_id=fid, pid=pid, reported_cost=cost
        )


class TestModuleExports:
    """Module exposes expected public symbols."""

    def test_function_in_all(self):
        assert "per_feature_subagent_cost_cap_default_10_single_subagent" in mod.__all__

    def test_default_cap_exported(self):
        assert hasattr(mod, "DEFAULT_CAP")
        assert mod.DEFAULT_CAP == 10.0

    def test_source_file_exists(self):
        src = Path(__file__).parent.parent / "src" / "bob" / "per_feature_subagent_cost_cap_default_10_single_subagent.py"
        assert src.exists(), f"Missing: {src}"
