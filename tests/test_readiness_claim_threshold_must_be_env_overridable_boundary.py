"""Boundary tests for the env-overridable readiness-claim threshold
(9ec1f44d-8e45-4441-859f-5ed30c83f484).

Empty, zero, or minimum input returns a well-defined result rather than raising
(boundary case). Covers resolve_readiness_override() (lenient) and the extreme
[0,1] endpoints of parse_readiness_threshold().
"""

from __future__ import annotations

import pytest

from bob.orchestrator.feature_claim import (
    parse_readiness_threshold,
    resolve_readiness_override,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB_READINESS_THRESHOLD", raising=False)


class TestResolveReadinessOverrideBoundary:
    def test_no_env_var_returns_none(self):
        assert resolve_readiness_override() is None

    def test_empty_string_returns_none(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": ""}) is None

    def test_whitespace_only_returns_none(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "   "}) is None

    def test_zero_returns_zero_float(self):
        result = resolve_readiness_override({"BOB_READINESS_THRESHOLD": "0"})
        assert result == 0.0
        assert isinstance(result, float)

    def test_one_returns_one_float(self):
        result = resolve_readiness_override({"BOB_READINESS_THRESHOLD": "1"})
        assert result == 1.0

    def test_minimum_positive_returned(self):
        result = resolve_readiness_override({"BOB_READINESS_THRESHOLD": "0.01"})
        assert result == pytest.approx(0.01)

    def test_out_of_range_returns_none_not_raise(self):
        """Out-of-range value is a well-defined None, not an exception."""
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "2.0"}) is None

    def test_malformed_returns_none_not_raise(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "xyz"}) is None


class TestParseReadinessThresholdBoundary:
    def test_lower_bound_zero_accepted(self):
        assert parse_readiness_threshold("0") == 0.0

    def test_upper_bound_one_accepted(self):
        assert parse_readiness_threshold("1") == 1.0

    def test_minimum_positive_accepted(self):
        assert parse_readiness_threshold("0.001") == pytest.approx(0.001)

    def test_returns_float(self):
        assert isinstance(parse_readiness_threshold("0.5"), float)
