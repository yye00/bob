"""Error tests: invalid input raises ValueError and does not silently succeed."""

from __future__ import annotations

import pytest

from hippy.rccl_autotune_sweep import (
    RcclConfig,
    TuneKey,
    AutotuneError,
    prune_search_space,
    tune_once_and_cache,
    default_config_grid,
)


def _perfect(config, *, tuning_enabled):
    return 0


def _flat_perf(config):
    return 10.0


def test_prune_rejects_non_list_grid():
    with pytest.raises(ValueError):
        prune_search_space("not-a-list", arch="gfx90a", size_bytes=1024, max_configs=8)


def test_prune_rejects_empty_grid():
    with pytest.raises(ValueError):
        prune_search_space([], arch="gfx90a", size_bytes=1024, max_configs=8)


def test_prune_rejects_negative_max_configs():
    grid = default_config_grid()
    with pytest.raises(ValueError):
        prune_search_space(grid, arch="gfx90a", size_bytes=1024, max_configs=-3)


def test_prune_rejects_non_int_size():
    grid = default_config_grid()
    with pytest.raises(ValueError):
        prune_search_space(grid, arch="gfx90a", size_bytes="big", max_configs=8)


def test_config_rejects_negative_chunk_size():
    with pytest.raises(ValueError):
        RcclConfig("Simple", "Ring", 4, -1)


def test_tune_key_rejects_empty_collective():
    with pytest.raises(ValueError):
        TuneKey(collective="", size_range="1M", ngpus=8, arch="gfx90a")


def test_tune_rejects_empty_candidates():
    key = TuneKey(collective="all_reduce", size_range="1M", ngpus=8, arch="gfx90a")
    with pytest.raises(ValueError):
        tune_once_and_cache(key, [], correctness_fn=_perfect, perf_fn=_flat_perf,
                            cache={}, size_bytes=1024)


def test_tune_rejects_non_config_candidate():
    key = TuneKey(collective="all_reduce", size_range="1M", ngpus=8, arch="gfx90a")
    with pytest.raises(ValueError):
        tune_once_and_cache(key, ["nope"], correctness_fn=_perfect, perf_fn=_flat_perf,
                            cache={}, size_bytes=1024)


def test_tune_rejects_non_callable_correctness_fn():
    key = TuneKey(collective="all_reduce", size_range="1M", ngpus=8, arch="gfx90a")
    cfg = RcclConfig("Simple", "Ring", 4, 1024)
    with pytest.raises(ValueError):
        tune_once_and_cache(key, [cfg], correctness_fn=None, perf_fn=_flat_perf,
                            cache={}, size_bytes=1024)


def test_tune_rejects_bad_key_type():
    cfg = RcclConfig("Simple", "Ring", 4, 1024)
    with pytest.raises(ValueError):
        tune_once_and_cache("not-a-key", [cfg], correctness_fn=_perfect,
                            perf_fn=_flat_perf, cache={}, size_bytes=1024)


def test_tune_rejects_negative_noise_fraction():
    key = TuneKey(collective="all_reduce", size_range="1M", ngpus=8, arch="gfx90a")
    cfg = RcclConfig("Simple", "Ring", 4, 1024)
    with pytest.raises(ValueError):
        tune_once_and_cache(key, [cfg], correctness_fn=_perfect, perf_fn=_flat_perf,
                            cache={}, size_bytes=1024, noise_fraction=-0.1)
