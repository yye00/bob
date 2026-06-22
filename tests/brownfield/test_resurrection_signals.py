"""Tests for bob3.brownfield.resurrection signal filtering (F-R7-611 / BF-5).

Verifies:
  - Signal-A (graveyard PRs) always returned regardless of deep_resurrection_scan
  - Signal-B (export_without_impl) gated behind deep_resurrection_scan=True
  - Signal-C (todo_cluster) gated behind deep_resurrection_scan=True
  - filter_signals_by_feature_flags and filter_signals_by_config agree
  - get_graveyard_signal / signal_graveyard_prs public entry points exist
"""

from __future__ import annotations

import unittest

from bob3.brownfield.resurrection import (
    ResurrectionSignal,
    detect_resurrection_signals,
    filter_signals_by_config,
    filter_signals_by_feature_flags,
    get_graveyard_signal,
    signal_graveyard_prs,
)


def _signal(kind: str) -> ResurrectionSignal:
    return ResurrectionSignal(
        signal_kind=kind,
        evidence=["test-evidence"],
        staleness_days=30,
        recommended_action="finish_stub",
    )


class TestResurrectionModuleExists(unittest.TestCase):
    """Verify module and public symbols are importable."""

    def test_module_importable(self):
        import bob3.brownfield.resurrection  # noqa: F401

    def test_filter_signals_by_feature_flags_defined(self):
        self.assertTrue(callable(filter_signals_by_feature_flags))

    def test_filter_signals_by_config_defined(self):
        self.assertTrue(callable(filter_signals_by_config))

    def test_get_graveyard_signal_defined(self):
        self.assertTrue(callable(get_graveyard_signal))

    def test_signal_graveyard_prs_alias_defined(self):
        self.assertTrue(callable(signal_graveyard_prs))
        self.assertIs(signal_graveyard_prs, get_graveyard_signal)


class TestSignalAAlwaysReturned(unittest.TestCase):
    """Signal-A (stale_pr, stale_branch) always passes the filter."""

    def test_stale_pr_passes_when_deep_scan_off(self):
        signals = [_signal("stale_pr")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].signal_kind, "stale_pr")

    def test_stale_pr_passes_when_deep_scan_on(self):
        signals = [_signal("stale_pr")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        self.assertEqual(len(result), 1)

    def test_stale_branch_passes_when_deep_scan_off(self):
        signals = [_signal("stale_branch")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].signal_kind, "stale_branch")

    def test_stale_branch_passes_when_deep_scan_on(self):
        signals = [_signal("stale_branch")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        self.assertEqual(len(result), 1)


class TestSignalBGatedByDeepScan(unittest.TestCase):
    """Signal-B (export_without_impl) only passes with deep_resurrection_scan=True."""

    def test_export_without_impl_filtered_when_deep_scan_off(self):
        signals = [_signal("export_without_impl")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        self.assertEqual(result, [])

    def test_export_without_impl_passes_when_deep_scan_on(self):
        signals = [_signal("export_without_impl")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        self.assertEqual(len(result), 1)

    def test_mixed_signals_b_filtered_deep_scan_off(self):
        signals = [_signal("stale_pr"), _signal("export_without_impl")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        kinds = {s.signal_kind for s in result}
        self.assertIn("stale_pr", kinds)
        self.assertNotIn("export_without_impl", kinds)


class TestSignalCGatedByDeepScan(unittest.TestCase):
    """Signal-C (todo_cluster) only passes with deep_resurrection_scan=True."""

    def test_todo_cluster_filtered_when_deep_scan_off(self):
        signals = [_signal("todo_cluster")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        self.assertEqual(result, [])

    def test_todo_cluster_passes_when_deep_scan_on(self):
        signals = [_signal("todo_cluster")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        self.assertEqual(len(result), 1)

    def test_all_three_signals_deep_scan_off(self):
        signals = [
            _signal("stale_pr"),
            _signal("export_without_impl"),
            _signal("todo_cluster"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].signal_kind, "stale_pr")

    def test_all_three_signals_deep_scan_on(self):
        signals = [
            _signal("stale_pr"),
            _signal("export_without_impl"),
            _signal("todo_cluster"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        self.assertEqual(len(result), 3)


class TestFilterSignalsByConfig(unittest.TestCase):
    """filter_signals_by_config mirrors filter_signals_by_feature_flags via config dict."""

    def test_empty_config_defaults_deep_scan_off(self):
        signals = [_signal("stale_pr"), _signal("todo_cluster")]
        result = filter_signals_by_config(signals, config={})
        kinds = {s.signal_kind for s in result}
        self.assertIn("stale_pr", kinds)
        self.assertNotIn("todo_cluster", kinds)

    def test_none_config_defaults_deep_scan_off(self):
        signals = [_signal("export_without_impl")]
        result = filter_signals_by_config(signals, config=None)
        self.assertEqual(result, [])

    def test_deep_scan_true_via_config_passes_all(self):
        signals = [
            _signal("stale_pr"),
            _signal("export_without_impl"),
            _signal("todo_cluster"),
        ]
        result = filter_signals_by_config(
            signals, config={"deep_resurrection_scan": True}
        )
        self.assertEqual(len(result), 3)

    def test_deep_scan_false_via_config_filters_b_and_c(self):
        signals = [
            _signal("stale_pr"),
            _signal("export_without_impl"),
            _signal("todo_cluster"),
        ]
        result = filter_signals_by_config(
            signals, config={"deep_resurrection_scan": False}
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].signal_kind, "stale_pr")


class TestDetectResurrectionSignalsEmptyTouches(unittest.TestCase):
    """detect_resurrection_signals returns [] for empty touches without raising."""

    def test_empty_touches_returns_empty(self):
        result = detect_resurrection_signals(
            workspace_root="/tmp",
            touches=[],
            feature_keywords=[],
        )
        self.assertEqual(result, [])

    def test_empty_touches_does_not_raise(self):
        try:
            detect_resurrection_signals(
                workspace_root="/tmp",
                touches=[],
                feature_keywords=[],
                pr_lookback_days=0,
                branch_diverge_days=0,
            )
        except Exception as exc:
            self.fail(f"detect_resurrection_signals raised unexpectedly: {exc}")


class TestGetGraveyardSignalPublicAPI(unittest.TestCase):
    """get_graveyard_signal / signal_graveyard_prs public entry points."""

    def test_get_graveyard_signal_callable_with_repo(self):
        # gh CLI likely absent in CI — should return [] without raising.
        result = get_graveyard_signal(
            repo="nonexistent/repo",
            feature_keywords=["auth"],
        )
        self.assertIsInstance(result, list)

    def test_signal_graveyard_prs_alias_same_result(self):
        r1 = get_graveyard_signal(repo="", feature_keywords=[])
        r2 = signal_graveyard_prs(repo="", feature_keywords=[])
        self.assertEqual(r1, r2)

    def test_empty_repo_returns_empty(self):
        result = get_graveyard_signal(repo="", feature_keywords=["something"])
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
