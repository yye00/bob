"""Error-path tests for bob3.startup_crash_exempt — invalid inputs raise ValueError.

Each test verifies that the function raises ValueError and does NOT silently
succeed when given a nonsensical or incorrectly-typed argument.
"""
from __future__ import annotations

import pytest

from bob3.startup_crash_exempt import (
    exponential_backoff_seconds,
    try_exempt,
)


class TestTryExemptInvalidInputRaisesValueError:
    """try_exempt raises ValueError for invalid types and does not silently succeed."""

    def test_non_int_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=None, workspace=None, exempt_counter="0")  # type: ignore[arg-type]

    def test_float_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=None, workspace=None, exempt_counter=0.0)  # type: ignore[arg-type]

    def test_list_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=None, workspace=None, exempt_counter=[])  # type: ignore[arg-type]

    def test_none_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=None, workspace=None, exempt_counter=None)  # type: ignore[arg-type]

    def test_int_like_string_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=None, workspace=None, exempt_counter="5")  # type: ignore[arg-type]

    def test_non_string_exit_signature_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=123, workspace=None, exempt_counter=0)  # type: ignore[arg-type]

    def test_list_exit_signature_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=["cert error"], workspace=None, exempt_counter=0)  # type: ignore[arg-type]

    def test_bytes_exit_signature_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            try_exempt(exit_signature=b"cert error", workspace=None, exempt_counter=0)  # type: ignore[arg-type]

    def test_error_message_is_descriptive(self) -> None:
        with pytest.raises(ValueError, match="exempt_counter"):
            try_exempt(exit_signature=None, workspace=None, exempt_counter="bad")  # type: ignore[arg-type]

    def test_exit_signature_type_error_message_mentions_type(self) -> None:
        with pytest.raises(ValueError, match="exit_signature"):
            try_exempt(exit_signature=42, workspace=None, exempt_counter=0)  # type: ignore[arg-type]


class TestExponentialBackoffInvalidInputRaisesValueError:
    """exponential_backoff_seconds raises ValueError for non-integer counters."""

    def test_string_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            exponential_backoff_seconds("0")  # type: ignore[arg-type]

    def test_float_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            exponential_backoff_seconds(0.0)  # type: ignore[arg-type]

    def test_none_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            exponential_backoff_seconds(None)  # type: ignore[arg-type]

    def test_list_counter_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            exponential_backoff_seconds([])  # type: ignore[arg-type]

    def test_error_message_mentions_exempt_counter(self) -> None:
        with pytest.raises(ValueError, match="exempt_counter"):
            exponential_backoff_seconds("five")  # type: ignore[arg-type]
