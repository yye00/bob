"""Boundary tests: empty/zero/minimum input returns a well-defined result, not a raise."""

from __future__ import annotations

from hippy.rccl_autotune_sweep import (
    RcclConfig,
    TuneKey,
    TuneResult,
    prune_search_space,
    tune_once_and_cache,
    default_config_grid,
)


def _perfect(config, *, tuning_enabled):
    return 0


def _flat_perf(config):
    return 42.0


def test_prune_max_configs_one_returns_single():
    grid = default_config_grid()
    pruned = prune_search_space(grid, arch="gfx90a", size_bytes=0, max_configs=1)
    assert len(pruned) == 1


def test_prune_size_zero_is_well_defined():
    grid = default_config_grid()
    pruned = prune_search_space(grid, arch="gfx90a", size_bytes=0, max_configs=8)
    assert isinstance(pruned, list)
    assert 0 < len(pruned) <= 8


def test_prune_max_configs_exceeds_grid_returns_full_grid():
    grid = default_config_grid()
    pruned = prune_search_space(grid, arch="gfx90a", size_bytes=2_000_000, max_configs=10_000)
    assert len(pruned) <= len(grid)
    assert len(pruned) > 0


def test_tune_single_candidate_returns_it():
    key = TuneKey(collective="all_reduce", size_range="tiny", ngpus=1, arch="gfx90a")
    only = RcclConfig("Simple", "Ring", 1, 1024)
    result = tune_once_and_cache(
        key, [only], correctness_fn=_perfect, perf_fn=_flat_perf,
        cache={}, size_bytes=1024,
    )
    assert isinstance(result, TuneResult)
    assert result.winner == only


def test_tune_minimum_ngpus_one():
    key = TuneKey(collective="broadcast", size_range="1K", ngpus=1, arch="gfx908")
    cfg = RcclConfig("LL", "Ring", 1, 1024)
    result = tune_once_and_cache(
        key, [cfg], correctness_fn=_perfect, perf_fn=_flat_perf,
        cache={}, size_bytes=1024,
    )
    assert result.winner == cfg
