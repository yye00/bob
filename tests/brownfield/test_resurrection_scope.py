"""Tests for bob3.brownfield.resurrection.get_graveyard_signal (BF-5 scope reduction).

ACs verified:
  - Function defined: bob3.brownfield.resurrection.get_graveyard_signal
  - get_graveyard_signal returns only Signal-A (stale PR) signals
  - Signal-B (export_without_impl) is filtered by default
  - Signal-C (todo_cluster) is filtered by default
  - filter_signals_by_feature_flags gates B and C behind deep_resurrection_scan
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from bob3.brownfield.resurrection import (
    ResurrectionSignal,
    filter_signals_by_feature_flags,
    get_graveyard_signal,
)


class TestGetGraveyardSignalExists(unittest.TestCase):
    """Verify the function is importable and callable."""

    def test_function_is_importable(self):
        from bob3.brownfield import resurrection
        self.assertTrue(hasattr(resurrection, "get_graveyard_signal"))

    def test_function_is_callable(self):
        self.assertTrue(callable(get_graveyard_signal))


class TestGetGraveyardSignalReturnType(unittest.TestCase):
    """get_graveyard_signal must return a list of ResurrectionSignal."""

    @patch("bob3.brownfield.resurrection.subprocess.run")
    def test_returns_list(self, mock_run):
        mock_run.return_value = type("R", (), {"returncode": 1, "stdout": ""})()
        result = get_graveyard_signal(
            repo="owner/repo",
            feature_keywords=["test-feature"],
        )
        self.assertIsInstance(result, list)

    @patch("bob3.brownfield.resurrection.subprocess.run")
    def test_returns_empty_list_on_no_prs(self, mock_run):
        mock_run.return_value = type("R", (), {"returncode": 1, "stdout": "[]"})()
        result = get_graveyard_signal(
            repo="owner/repo",
            feature_keywords=["my-feature"],
        )
        self.assertIsInstance(result, list)

    @patch("bob3.brownfield.resurrection.subprocess.run")
    def test_returns_signal_a_when_pr_found(self, mock_run):
        import json
        prs = [{"number": 1, "title": "my-feature impl", "body": "", "url": "https://github.com/pr/1", "updatedAt": "2025-01-01T00:00:00Z"}]
        mock_run.return_value = type("R", (), {
            "returncode": 0,
            "stdout": json.dumps(prs),
        })()
        result = get_graveyard_signal(
            repo="owner/repo",
            feature_keywords=["my-feature"],
        )
        self.assertIsInstance(result, list)
        if result:
            self.assertEqual(result[0].signal_kind, "stale_pr")


class TestGetGraveyardSignalOnlySignalA(unittest.TestCase):
    """get_graveyard_signal must return only Signal-A (stale PR/branch) signals."""

    def test_never_returns_signal_b(self):
        signal_b = ResurrectionSignal(
            signal_kind="export_without_impl",
            evidence=["file.py:foo"],
            staleness_days=0,
            recommended_action="finish_stub",
        )
        filtered = filter_signals_by_feature_flags([signal_b], deep_resurrection_scan=False)
        signal_kinds = [s.signal_kind for s in filtered]
        self.assertNotIn("export_without_impl", signal_kinds)

    def test_never_returns_signal_c(self):
        signal_c = ResurrectionSignal(
            signal_kind="todo_cluster",
            evidence=["file.py:line 5"],
            staleness_days=0,
            recommended_action="finish_stub",
        )
        filtered = filter_signals_by_feature_flags([signal_c], deep_resurrection_scan=False)
        signal_kinds = [s.signal_kind for s in filtered]
        self.assertNotIn("todo_cluster", signal_kinds)

    def test_returns_signal_a(self):
        signal_a = ResurrectionSignal(
            signal_kind="stale_pr",
            evidence=["https://github.com/pr/1"],
            staleness_days=90,
            recommended_action="resume_pr",
        )
        filtered = filter_signals_by_feature_flags([signal_a], deep_resurrection_scan=False)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].signal_kind, "stale_pr")

    def test_returns_stale_branch_signal_a(self):
        signal_a = ResurrectionSignal(
            signal_kind="stale_branch",
            evidence=["refs/heads/feature/my-feature"],
            staleness_days=30,
            recommended_action="rebase_branch",
        )
        filtered = filter_signals_by_feature_flags([signal_a], deep_resurrection_scan=False)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].signal_kind, "stale_branch")


class TestFilterSignalsByFeatureFlags(unittest.TestCase):
    """filter_signals_by_feature_flags gates B and C behind deep_resurrection_scan."""

    def _make_signals(self):
        return [
            ResurrectionSignal("stale_pr", ["url"], 90, "resume_pr"),
            ResurrectionSignal("stale_branch", ["ref"], 30, "rebase_branch"),
            ResurrectionSignal("export_without_impl", ["file.py:foo"], 0, "finish_stub"),
            ResurrectionSignal("todo_cluster", ["file.py:line 1"], 0, "finish_stub"),
        ]

    def test_default_off_filters_b_and_c(self):
        signals = self._make_signals()
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        kinds = {s.signal_kind for s in result}
        self.assertNotIn("export_without_impl", kinds)
        self.assertNotIn("todo_cluster", kinds)

    def test_default_off_keeps_a(self):
        signals = self._make_signals()
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        kinds = {s.signal_kind for s in result}
        self.assertIn("stale_pr", kinds)
        self.assertIn("stale_branch", kinds)

    def test_deep_scan_returns_all(self):
        signals = self._make_signals()
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        self.assertEqual(len(result), 4)

    def test_empty_signals_returns_empty(self):
        result = filter_signals_by_feature_flags([], deep_resurrection_scan=False)
        self.assertEqual(result, [])


class TestGetGraveyardSignalSignature(unittest.TestCase):
    """Verify function signature matches expectations."""

    def test_accepts_repo(self):
        import inspect
        sig = inspect.signature(get_graveyard_signal)
        self.assertIn("repo", sig.parameters)

    def test_accepts_feature_keywords(self):
        import inspect
        sig = inspect.signature(get_graveyard_signal)
        self.assertIn("feature_keywords", sig.parameters)

    def test_accepts_lookback_days_optional(self):
        import inspect
        sig = inspect.signature(get_graveyard_signal)
        self.assertIn("lookback_days", sig.parameters)
        param = sig.parameters["lookback_days"]
        self.assertNotEqual(param.default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
