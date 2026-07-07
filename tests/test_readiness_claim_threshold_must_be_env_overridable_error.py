"""Error-path tests for the env-overridable readiness-claim threshold
(9ec1f44d-8e45-4441-859f-5ed30c83f484).

Invalid input passed to the strict parser must raise ValueError and the
function must NOT silently succeed. The lenient env resolver must never
silently return a garbage float that would corrupt claim gating.
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


class TestParseReadinessThresholdRaises:
    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("not_a_number")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("   ")

    def test_above_range_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("1.5")

    def test_below_range_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("-0.1")

    def test_nan_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("nan")

    def test_inf_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold("inf")

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold(0.5)  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises(ValueError):
            parse_readiness_threshold(None)  # type: ignore[arg-type]


class TestResolverDoesNotSilentlyCorruptGating:
    def test_malformed_env_does_not_return_a_float(self):
        """Malformed override must fall back to None, not a bogus float floor."""
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "garbage"}) is None

    def test_nan_env_does_not_return_a_float(self):
        """'nan' would make every readiness comparison fail — must be rejected."""
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "nan"}) is None

    def test_out_of_range_env_does_not_return_a_float(self):
        assert resolve_readiness_override({"BOB_READINESS_THRESHOLD": "5"}) is None
