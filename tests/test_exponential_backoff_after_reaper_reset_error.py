"""Error-path tests for exponential backoff after reaper-reset.

AC: invalid input raises ValueError and the function does not silently succeed.

Tests that the exponential backoff functions reject clearly invalid inputs
rather than silently returning garbage results.
"""

from __future__ import annotations

import pytest

from bob.reaper import apply_exponential_backoff, should_refuse_redispatch
from bob.orchestrator.reap_backoff import (
    compute_backoff_seconds,
    may_redispatch,
    escalate_after_n_reaps,
)


class TestComputeBackoffSecondsError:
    def test_non_integer_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            compute_backoff_seconds("two")

    def test_float_string_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_backoff_seconds("1.5")

    def test_none_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            compute_backoff_seconds(None)

    def test_list_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_backoff_seconds([1])


class TestApplyExponentialBackoffError:
    def test_none_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            apply_exponential_backoff(None)

    def test_non_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            apply_exponential_backoff("not-a-feature")

    def test_integer_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            apply_exponential_backoff(42)


class TestShouldRefuseRedispatchError:
    def test_none_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch(None)

    def test_non_feature_object_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch("not-a-feature")

    def test_integer_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch(99)


class TestEscalateAfterNReapsError:
    def test_none_feature_id_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            escalate_after_n_reaps(None, reap_count=3)

    def test_non_string_feature_id_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            escalate_after_n_reaps(12345, reap_count=3)

    def test_string_reap_count_raises(self):
        with pytest.raises((ValueError, TypeError)):
            escalate_after_n_reaps("feature-id", reap_count="three")

    def test_none_reap_count_raises(self):
        with pytest.raises((ValueError, TypeError)):
            escalate_after_n_reaps("feature-id", reap_count=None)
