"""Tests for hippy.rccl_autotune_sweep — tune-once/cache + config pruning + parity."""

from __future__ import annotations

import pytest

from hippy.rccl_autotune_sweep import (
    RcclConfig,
    TuneKey,
    TuneResult,
    AutotuneError,
    prune_search_space,
    tune_once_and_cache,
    default_config_grid,
)


# ---------------------------------------------------------------------------
# helpers: fake correctness + perf oracles
# ---------------------------------------------------------------------------

def _perfect_correctness(config, *, tuning_enabled):
    """Every config is bit-correct with tuning on or off."""
    return 0  # #wrong == 0


def _corrupting_correctness(bad_protocol):
    def check(config, *, tuning_enabled):
        if tuning_enabled and config.protocol == bad_protocol:
            return 7  # #wrong > 0 -> must be rejected
        return 0
    return check


def _perf_by_protocol(scores):
    """Lower runtime is better; return runtime keyed on protocol."""
    def measure(config):
        return scores.get(config.protocol, 100.0)
    return measure


# ---------------------------------------------------------------------------
# RcclConfig
# ---------------------------------------------------------------------------

def test_rccl_config_is_hashable_and_frozen():
    c = RcclConfig(protocol="Simple", algorithm="Ring", channels=4, chunk_size=131072)
    assert hash(c) == hash(RcclConfig(protocol="Simple", algorithm="Ring", channels=4, chunk_size=131072))
    with pytest.raises(Exception):
        c.protocol = "LL"


def test_rccl_config_env_knobs():
    c = RcclConfig(protocol="LL128", algorithm="Tree", channels=8, chunk_size=524288)
    env = c.to_env()
    assert env["NCCL_PROTO"] == "LL128"
    assert env["NCCL_ALGO"] == "Tree"
    assert env["NCCL_MIN_NCHANNELS"] == "8"


def test_rccl_config_rejects_bad_protocol():
    with pytest.raises(ValueError):
        RcclConfig(protocol="Bogus", algorithm="Ring", channels=4, chunk_size=1024)


def test_rccl_config_rejects_bad_algorithm():
    with pytest.raises(ValueError):
        RcclConfig(protocol="Simple", algorithm="Mesh", channels=4, chunk_size=1024)


def test_rccl_config_rejects_nonpositive_channels():
    with pytest.raises(ValueError):
        RcclConfig(protocol="Simple", algorithm="Ring", channels=0, chunk_size=1024)


# ---------------------------------------------------------------------------
# TuneKey
# ---------------------------------------------------------------------------

def test_tune_key_hashable_identity():
    k1 = TuneKey(collective="all_reduce", size_range="1M-4M", ngpus=8, arch="gfx90a")
    k2 = TuneKey(collective="all_reduce", size_range="1M-4M", ngpus=8, arch="gfx90a")
    assert k1 == k2 and hash(k1) == hash(k2)


def test_tune_key_rejects_bad_ngpus():
    with pytest.raises(ValueError):
        TuneKey(collective="all_reduce", size_range="1M", ngpus=0, arch="gfx90a")


# ---------------------------------------------------------------------------
# prune_search_space
# ---------------------------------------------------------------------------

def test_prune_bounds_to_max_configs():
    grid = default_config_grid()
    pruned = prune_search_space(grid, arch="gfx90a", size_bytes=2_000_000, max_configs=8)
    assert 0 < len(pruned) <= 8
    assert all(isinstance(c, RcclConfig) for c in pruned)


def test_prune_small_size_prefers_ll_protocols():
    grid = default_config_grid()
    pruned = prune_search_space(grid, arch="gfx90a", size_bytes=1024, max_configs=8)
    # small messages: latency-bound -> LL/LL128 should be represented
    protos = {c.protocol for c in pruned}
    assert protos & {"LL", "LL128"}
    # a tiny message should not keep giant chunk sizes
    assert all(c.chunk_size <= 262144 for c in pruned)


def test_prune_large_size_prefers_simple():
    grid = default_config_grid()
    pruned = prune_search_space(grid, arch="gfx90a", size_bytes=64_000_000, max_configs=8)
    protos = {c.protocol for c in pruned}
    assert "Simple" in protos


def test_prune_is_deterministic():
    grid = default_config_grid()
    a = prune_search_space(grid, arch="gfx90a", size_bytes=2_000_000, max_configs=6)
    b = prune_search_space(grid, arch="gfx90a", size_bytes=2_000_000, max_configs=6)
    assert a == b


def test_prune_rejects_bad_max_configs():
    grid = default_config_grid()
    with pytest.raises(ValueError):
        prune_search_space(grid, arch="gfx90a", size_bytes=1024, max_configs=0)


def test_prune_rejects_empty_arch():
    grid = default_config_grid()
    with pytest.raises(ValueError):
        prune_search_space(grid, arch="", size_bytes=1024, max_configs=8)


def test_prune_rejects_negative_size():
    grid = default_config_grid()
    with pytest.raises(ValueError):
        prune_search_space(grid, arch="gfx90a", size_bytes=-1, max_configs=8)


# ---------------------------------------------------------------------------
# tune_once_and_cache
# ---------------------------------------------------------------------------

def _key():
    return TuneKey(collective="all_reduce", size_range="1M-4M", ngpus=8, arch="gfx90a")


def test_tune_selects_fastest_correct_config():
    key = _key()
    candidates = [
        RcclConfig("Simple", "Ring", 4, 131072),
        RcclConfig("LL128", "Tree", 8, 131072),
    ]
    cache = {}
    result = tune_once_and_cache(
        key,
        candidates,
        correctness_fn=_perfect_correctness,
        perf_fn=_perf_by_protocol({"Simple": 50.0, "LL128": 20.0}),
        cache=cache,
        size_bytes=2_000_000,
    )
    assert isinstance(result, TuneResult)
    assert result.winner.protocol == "LL128"
    assert result.from_cache is False
    assert key in cache


def test_tune_caches_and_second_call_does_not_resweep():
    key = _key()
    candidates = [RcclConfig("Simple", "Ring", 4, 131072)]
    cache = {}
    calls = {"n": 0}

    def counting_perf(config):
        calls["n"] += 1
        return 10.0

    tune_once_and_cache(key, candidates, correctness_fn=_perfect_correctness,
                        perf_fn=counting_perf, cache=cache, size_bytes=2_000_000)
    first_calls = calls["n"]
    r2 = tune_once_and_cache(key, candidates, correctness_fn=_perfect_correctness,
                             perf_fn=counting_perf, cache=cache, size_bytes=2_000_000)
    assert r2.from_cache is True
    assert calls["n"] == first_calls  # perf_fn NOT invoked again


def test_tune_rejects_config_that_corrupts_with_tuning_enabled():
    key = _key()
    candidates = [
        RcclConfig("LL128", "Tree", 8, 131072),  # fast but corrupts
        RcclConfig("Simple", "Ring", 4, 131072),  # slower but correct
    ]
    result = tune_once_and_cache(
        key,
        candidates,
        correctness_fn=_corrupting_correctness("LL128"),
        perf_fn=_perf_by_protocol({"LL128": 5.0, "Simple": 40.0}),
        cache={},
        size_bytes=2_000_000,
    )
    # LL128 wins on bandwidth but corrupts -> rejected; Simple must win.
    assert result.winner.protocol == "Simple"
    assert any(r.config.protocol == "LL128" and not r.correct for r in result.evaluations)


def test_tune_ab_gate_falls_back_to_baseline_when_not_faster():
    key = _key()
    baseline = RcclConfig("Simple", "Ring", 4, 131072)
    candidates = [RcclConfig("LL", "Ring", 2, 65536)]
    # tuned candidate is only marginally faster -> inside noise band -> keep baseline
    result = tune_once_and_cache(
        key,
        candidates,
        correctness_fn=_perfect_correctness,
        perf_fn=_perf_by_protocol({"Simple": 100.0, "LL": 99.0}),
        cache={},
        size_bytes=2_000_000,
        baseline_config=baseline,
        noise_fraction=0.05,
    )
    assert result.winner == baseline
    assert result.beat_baseline is False


def test_tune_ab_gate_accepts_when_clearly_faster():
    key = _key()
    baseline = RcclConfig("Simple", "Ring", 4, 131072)
    candidates = [RcclConfig("LL128", "Tree", 8, 131072)]
    result = tune_once_and_cache(
        key,
        candidates,
        correctness_fn=_perfect_correctness,
        perf_fn=_perf_by_protocol({"Simple": 100.0, "LL128": 50.0}),
        cache={},
        size_bytes=2_000_000,
        baseline_config=baseline,
        noise_fraction=0.05,
    )
    assert result.winner.protocol == "LL128"
    assert result.beat_baseline is True


def test_tune_raises_when_no_config_is_correct():
    key = _key()
    candidates = [RcclConfig("LL128", "Tree", 8, 131072)]
    with pytest.raises(AutotuneError):
        tune_once_and_cache(
            key,
            candidates,
            correctness_fn=_corrupting_correctness("LL128"),
            perf_fn=_perf_by_protocol({"LL128": 5.0}),
            cache={},
            size_bytes=2_000_000,
        )


# ---------------------------------------------------------------------------
# integration: hippy.audit_exemptions
# ---------------------------------------------------------------------------

def test_integration_audit_exemptions_importable():
    import hippy.audit_exemptions as ae
    assert hasattr(ae, "classify_op_exemption")
