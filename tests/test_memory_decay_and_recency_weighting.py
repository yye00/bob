"""Tests for src/bob3/memory_decay_and_recency_weighting.py."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from bob3.memory_decay_and_recency_weighting import (
    MemoryDecayConfig,
    compute_decay_weight,
    get_decay_config,
    top_k_learnings,
    weight_learnings,
)


# ---------------------------------------------------------------------------
# get_decay_config
# ---------------------------------------------------------------------------


class TestGetDecayConfig:
    def test_defaults_to_30_days(self):
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items() if k != "BOB3_LESSON_HALF_LIFE_DAYS"}
            with patch.dict(os.environ, env, clear=True):
                config = get_decay_config()
        assert config.half_life_days == 30.0

    def test_reads_env_var(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "60"}):
            config = get_decay_config()
        assert config.half_life_days == 60.0

    def test_fractional_half_life(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "7.5"}):
            config = get_decay_config()
        assert config.half_life_days == 7.5

    def test_raises_for_non_numeric(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "not-a-number"}):
            with pytest.raises(ValueError, match="not a valid number"):
                get_decay_config()

    def test_raises_for_zero(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "0"}):
            with pytest.raises(ValueError, match="must be positive"):
                get_decay_config()

    def test_raises_for_negative(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "-10"}):
            with pytest.raises(ValueError, match="must be positive"):
                get_decay_config()

    def test_context_pool_has_shorter_half_life(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "30"}):
            config = get_decay_config()
        assert config.context_half_life_days < config.half_life_days

    def test_long_term_pool_has_longer_half_life(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "30"}):
            config = get_decay_config()
        assert config.long_term_half_life_days > config.half_life_days

    def test_context_half_life_is_half_of_base(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "30"}):
            config = get_decay_config()
        assert config.context_half_life_days == 15.0

    def test_long_term_half_life_is_three_times_base(self):
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "30"}):
            config = get_decay_config()
        assert config.long_term_half_life_days == 90.0


# ---------------------------------------------------------------------------
# MemoryDecayConfig.half_life_for_pool
# ---------------------------------------------------------------------------


class TestHalfLifeForPool:
    def setup_method(self):
        self.config = MemoryDecayConfig(
            half_life_days=30.0,
            context_half_life_days=15.0,
            long_term_half_life_days=90.0,
        )

    def test_context_pool(self):
        assert self.config.half_life_for_pool("context") == 15.0

    def test_long_term_pool(self):
        assert self.config.half_life_for_pool("long_term") == 90.0

    def test_lessons_pool_uses_base(self):
        assert self.config.half_life_for_pool("lessons") == 30.0

    def test_none_pool_uses_base(self):
        assert self.config.half_life_for_pool(None) == 30.0

    def test_unknown_pool_uses_base(self):
        assert self.config.half_life_for_pool("facts") == 30.0


# ---------------------------------------------------------------------------
# compute_decay_weight
# ---------------------------------------------------------------------------


class TestComputeDecayWeight:
    def setup_method(self):
        self.config = MemoryDecayConfig(
            half_life_days=30.0,
            context_half_life_days=15.0,
            long_term_half_life_days=90.0,
        )
        self.now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)

    def test_brand_new_weight_is_one(self):
        w = compute_decay_weight(self.now.isoformat(), self.config, now=self.now)
        assert abs(w - 1.0) < 1e-9

    def test_exactly_one_half_life_gives_half(self):
        ts = self.now - timedelta(days=30)
        w = compute_decay_weight(ts.isoformat(), self.config, now=self.now)
        assert abs(w - 0.5) < 1e-9

    def test_two_half_lives_gives_quarter(self):
        ts = self.now - timedelta(days=60)
        w = compute_decay_weight(ts.isoformat(), self.config, now=self.now)
        assert abs(w - 0.25) < 1e-9

    def test_weight_between_zero_and_one(self):
        ts = self.now - timedelta(days=100)
        w = compute_decay_weight(ts.isoformat(), self.config, now=self.now)
        assert 0.0 < w < 1.0

    def test_future_timestamp_gives_weight_one(self):
        ts = self.now + timedelta(days=5)
        w = compute_decay_weight(ts.isoformat(), self.config, now=self.now)
        assert abs(w - 1.0) < 1e-9

    def test_context_pool_decays_faster(self):
        ts = self.now - timedelta(days=15)
        w_default = compute_decay_weight(ts.isoformat(), self.config, None, now=self.now)
        w_context = compute_decay_weight(ts.isoformat(), self.config, "context", now=self.now)
        assert w_context < w_default

    def test_long_term_pool_decays_slower(self):
        ts = self.now - timedelta(days=30)
        w_default = compute_decay_weight(ts.isoformat(), self.config, None, now=self.now)
        w_long = compute_decay_weight(ts.isoformat(), self.config, "long_term", now=self.now)
        assert w_long > w_default

    def test_accepts_datetime_object(self):
        ts = self.now - timedelta(days=30)
        w = compute_decay_weight(ts, self.config, now=self.now)
        assert abs(w - 0.5) < 1e-9

    def test_accepts_z_suffix_iso(self):
        ts = (self.now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        w = compute_decay_weight(ts, self.config, now=self.now)
        assert abs(w - 0.5) < 1e-9

    def test_older_entries_have_lower_weight(self):
        ts_old = self.now - timedelta(days=90)
        ts_new = self.now - timedelta(days=10)
        w_old = compute_decay_weight(ts_old.isoformat(), self.config, now=self.now)
        w_new = compute_decay_weight(ts_new.isoformat(), self.config, now=self.now)
        assert w_old < w_new

    def test_uses_get_decay_config_when_none(self):
        ts = self.now - timedelta(days=30)
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "30"}):
            w = compute_decay_weight(ts.isoformat(), None, now=self.now)
        assert abs(w - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# weight_learnings
# ---------------------------------------------------------------------------


class TestWeightLearnings:
    def setup_method(self):
        self.config = MemoryDecayConfig(
            half_life_days=30.0,
            context_half_life_days=15.0,
            long_term_half_life_days=90.0,
        )
        self.now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)

    def _make_entry(self, days_ago: float, pool: str | None = None) -> dict:
        ts = self.now - timedelta(days=days_ago)
        entry = {"timestamp": ts.isoformat(), "lesson": f"Lesson from {days_ago}d ago"}
        if pool is not None:
            entry["pool"] = pool
        return entry

    def test_returns_list_same_length(self):
        entries = [self._make_entry(1), self._make_entry(10)]
        result = weight_learnings(entries, self.config, now=self.now)
        assert len(result) == 2

    def test_each_entry_has_decay_weight(self):
        entries = [self._make_entry(5)]
        result = weight_learnings(entries, self.config, now=self.now)
        assert "decay_weight" in result[0]

    def test_newer_entries_have_higher_weight(self):
        entries = [self._make_entry(5), self._make_entry(60)]
        result = weight_learnings(entries, self.config, now=self.now)
        weights = {e["lesson"]: e["decay_weight"] for e in result}
        assert weights["Lesson from 5d ago"] > weights["Lesson from 60d ago"]

    def test_does_not_mutate_originals(self):
        original = self._make_entry(10)
        originals_copy = dict(original)
        weight_learnings([original], self.config, now=self.now)
        assert original == originals_copy

    def test_missing_timestamp_gives_zero(self):
        entry = {"lesson": "No timestamp here"}
        result = weight_learnings([entry], self.config, now=self.now)
        assert result[0]["decay_weight"] == 0.0

    def test_invalid_timestamp_gives_zero(self):
        entry = {"timestamp": "not-a-date", "lesson": "Bad date"}
        result = weight_learnings([entry], self.config, now=self.now)
        assert result[0]["decay_weight"] == 0.0

    def test_empty_list_returns_empty(self):
        assert weight_learnings([], self.config, now=self.now) == []

    def test_per_entry_pool_overrides_default_pool(self):
        entry_ctx = self._make_entry(15, pool="context")
        entry_lt = self._make_entry(15, pool="long_term")
        result = weight_learnings([entry_ctx, entry_lt], self.config, now=self.now)
        w_ctx = result[0]["decay_weight"]
        w_lt = result[1]["decay_weight"]
        # context decays faster → lower weight for same age
        assert w_ctx < w_lt

    def test_uses_get_decay_config_when_none(self):
        entry = self._make_entry(0)
        with patch.dict(os.environ, {"BOB3_LESSON_HALF_LIFE_DAYS": "30"}):
            result = weight_learnings([entry], None, now=self.now)
        assert abs(result[0]["decay_weight"] - 1.0) < 0.01


# ---------------------------------------------------------------------------
# top_k_learnings
# ---------------------------------------------------------------------------


class TestTopKLearnings:
    def setup_method(self):
        self.config = MemoryDecayConfig(
            half_life_days=30.0,
            context_half_life_days=15.0,
            long_term_half_life_days=90.0,
        )
        self.now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)

    def _make_entry(self, days_ago: float) -> dict:
        ts = self.now - timedelta(days=days_ago)
        return {"timestamp": ts.isoformat(), "lesson": f"Lesson {days_ago}d ago"}

    def test_returns_k_entries(self):
        entries = [self._make_entry(i) for i in range(10)]
        result = top_k_learnings(entries, 3, self.config, now=self.now)
        assert len(result) == 3

    def test_returns_fewer_than_k_when_not_enough(self):
        entries = [self._make_entry(i) for i in range(2)]
        result = top_k_learnings(entries, 5, self.config, now=self.now)
        assert len(result) == 2

    def test_returns_most_recent_first(self):
        entries = [self._make_entry(50), self._make_entry(5), self._make_entry(20)]
        result = top_k_learnings(entries, 3, self.config, now=self.now)
        assert result[0]["lesson"] == "Lesson 5d ago"

    def test_all_entries_have_decay_weight(self):
        entries = [self._make_entry(i) for i in range(5)]
        result = top_k_learnings(entries, 5, self.config, now=self.now)
        for entry in result:
            assert "decay_weight" in entry

    def test_sorted_descending_by_weight(self):
        entries = [self._make_entry(i * 10) for i in range(5)]
        result = top_k_learnings(entries, 5, self.config, now=self.now)
        weights = [e["decay_weight"] for e in result]
        assert weights == sorted(weights, reverse=True)

    def test_empty_input_returns_empty(self):
        assert top_k_learnings([], 5, self.config, now=self.now) == []

    def test_k_zero_returns_empty(self):
        entries = [self._make_entry(1), self._make_entry(2)]
        result = top_k_learnings(entries, 0, self.config, now=self.now)
        assert result == []
