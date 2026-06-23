"""Tests for bob3.brownfield.resurrection — BF-5 Resurrection gate.

Covers:
  - Module and function existence
  - detect_resurrection_signals (Signals A, B, C)
  - write_resurrection_report
  - Integration: detect then write
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import patch

from bob3.brownfield.resurrection import (
    ResurrectionSignal,
    detect_resurrection_signals,
    detect_export_without_impl,
    detect_stale_branch,
    detect_todo_clusters,
    write_resurrection_report,
)


# ---------------------------------------------------------------------------
# Module existence checks
# ---------------------------------------------------------------------------


class TestModuleExists(unittest.TestCase):
    def test_module_importable(self):
        import bob3.brownfield.resurrection  # noqa: F401

    def test_detect_resurrection_signals_defined(self):
        from bob3.brownfield import resurrection
        self.assertTrue(hasattr(resurrection, "detect_resurrection_signals"))
        self.assertTrue(callable(resurrection.detect_resurrection_signals))

    def test_write_resurrection_report_defined(self):
        from bob3.brownfield import resurrection
        self.assertTrue(hasattr(resurrection, "write_resurrection_report"))
        self.assertTrue(callable(resurrection.write_resurrection_report))

    def test_resurrection_signal_dataclass_defined(self):
        sig = ResurrectionSignal(
            signal_kind="stale_pr",
            evidence=["https://github.com/org/repo/pull/1"],
            staleness_days=91,
            recommended_action="resume_pr",
        )
        self.assertEqual(sig.signal_kind, "stale_pr")


# ---------------------------------------------------------------------------
# detect_resurrection_signals — basic contracts
# ---------------------------------------------------------------------------


class TestDetectResurrectionSignalsContracts(unittest.TestCase):
    def test_returns_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_resurrection_signals(
                workspace_root=tmp,
                touches=[],
                feature_keywords=[],
                repo="",
            )
            self.assertIsInstance(result, list)

    def test_empty_touches_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_resurrection_signals(
                workspace_root=tmp,
                touches=[],
                feature_keywords=["feat"],
                repo="",
            )
            self.assertEqual(result, [])

    def test_nonexistent_file_skipped_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_resurrection_signals(
                workspace_root=tmp,
                touches=["does_not_exist.py"],
                feature_keywords=["feat"],
                repo="",
            )
            self.assertIsInstance(result, list)

    def test_signals_are_resurrection_signal_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "mod.py"
            p.write_text("# TODO: fix this\n# TODO: also this\n# TODO: and this\ndef fn(): pass\n")
            result = detect_resurrection_signals(
                workspace_root=tmp,
                touches=["mod.py"],
                feature_keywords=[],
                repo="",
                todo_cluster_min_size=3,
            )
            for sig in result:
                self.assertIsInstance(sig, ResurrectionSignal)


# ---------------------------------------------------------------------------
# Signal B — export_without_impl
# ---------------------------------------------------------------------------


class TestSignalBExportWithoutImpl(unittest.TestCase):
    def test_stub_body_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "stub.py").write_text(
                "__all__ = ['do_work']\ndef do_work():\n    pass\n"
            )
            sigs = detect_export_without_impl(workspace_root=tmp, touches=["stub.py"])
            kinds = [s.signal_kind for s in sigs]
            self.assertIn("export_without_impl", kinds)

    def test_implemented_body_not_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "impl.py").write_text(
                "__all__ = ['do_work']\ndef do_work():\n    return 42\n"
            )
            sigs = detect_export_without_impl(workspace_root=tmp, touches=["impl.py"])
            self.assertEqual(sigs, [])

    def test_no_all_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "no_all.py").write_text("def fn(): pass\n")
            sigs = detect_export_without_impl(workspace_root=tmp, touches=["no_all.py"])
            self.assertEqual(sigs, [])

    def test_not_implemented_error_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "ni.py").write_text(
                "__all__ = ['fn']\ndef fn():\n    raise NotImplementedError\n"
            )
            sigs = detect_export_without_impl(workspace_root=tmp, touches=["ni.py"])
            self.assertTrue(len(sigs) >= 1)
            self.assertEqual(sigs[0].signal_kind, "export_without_impl")
            self.assertEqual(sigs[0].recommended_action, "finish_stub")


# ---------------------------------------------------------------------------
# Signal C — todo_cluster
# ---------------------------------------------------------------------------


class TestSignalCTodoClusters(unittest.TestCase):
    def test_three_todos_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "todos.py").write_text(
                "# TODO: one\n# TODO: two\n# TODO: three\ndef fn(): pass\n"
            )
            sigs = detect_todo_clusters(workspace_root=tmp, touches=["todos.py"], min_size=3)
            self.assertTrue(len(sigs) >= 1)
            self.assertEqual(sigs[0].signal_kind, "todo_cluster")

    def test_two_todos_below_threshold_no_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "less.py").write_text(
                "# TODO: one\n# TODO: two\ndef fn(): pass\n"
            )
            sigs = detect_todo_clusters(workspace_root=tmp, touches=["less.py"], min_size=3)
            self.assertEqual(sigs, [])

    def test_fixme_counts_as_todo(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "fix.py").write_text(
                "# FIXME: a\n# FIXME: b\n# FIXME: c\ndef fn(): pass\n"
            )
            sigs = detect_todo_clusters(workspace_root=tmp, touches=["fix.py"], min_size=3)
            self.assertTrue(len(sigs) >= 1)

    def test_recommended_action_finish_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "t.py").write_text(
                "# TODO: a\n# TODO: b\n# TODO: c\ndef fn(): pass\n"
            )
            sigs = detect_todo_clusters(workspace_root=tmp, touches=["t.py"], min_size=3)
            self.assertEqual(sigs[0].recommended_action, "finish_stub")


# ---------------------------------------------------------------------------
# Signal A — stale branch
# ---------------------------------------------------------------------------


class TestSignalAStaleBranch(unittest.TestCase):
    def test_empty_touches_no_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_stale_branch(workspace_root=tmp, touches=[], min_diverge_days=30)
            self.assertEqual(result, [])

    @patch("bob3.brownfield.resurrection.subprocess.run")
    def test_non_stale_branch_no_signal(self, mock_run):
        import datetime
        future_date = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
        mock_run.return_value = type("R", (), {
            "returncode": 0,
            "stdout": f"feature/abc {future_date}\n",
        })()
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_stale_branch(workspace_root=tmp, touches=["src/foo.py"], min_diverge_days=30)
            self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# write_resurrection_report
# ---------------------------------------------------------------------------


class TestWriteResurrectionReport(unittest.TestCase):
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_resurrection_report(
                feature_id="feat-abc",
                signals=[],
                bob3_root=tmp,
            )
            self.assertTrue(pathlib.Path(path).exists())

    def test_path_contains_feature_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_resurrection_report(
                feature_id="feat-xyz",
                signals=[],
                bob3_root=tmp,
            )
            self.assertIn("feat-xyz", path)

    def test_report_contains_signal_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            sigs = [
                ResurrectionSignal(
                    signal_kind="stale_pr",
                    evidence=["https://github.com/org/repo/pull/1"],
                    staleness_days=91,
                    recommended_action="resume_pr",
                )
            ]
            path = write_resurrection_report(
                feature_id="feat-report",
                signals=sigs,
                bob3_root=tmp,
            )
            content = pathlib.Path(path).read_text()
            self.assertIn("stale_pr", content)
            self.assertIn("resume_pr", content)
            self.assertIn("91", content)

    def test_empty_signals_no_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_resurrection_report(
                feature_id="feat-empty",
                signals=[],
                bob3_root=tmp,
            )
            content = pathlib.Path(path).read_text()
            self.assertIn("feat-empty", content)

    def test_report_mentions_signal_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            sigs = [
                ResurrectionSignal("stale_pr", ["url"], 90, "resume_pr"),
                ResurrectionSignal("stale_branch", ["ref"], 30, "rebase_branch"),
            ]
            path = write_resurrection_report(
                feature_id="feat-multi",
                signals=sigs,
                bob3_root=tmp,
            )
            content = pathlib.Path(path).read_text()
            self.assertIn("2", content)


# ---------------------------------------------------------------------------
# Integration — detect then write
# ---------------------------------------------------------------------------


class TestIntegration(unittest.TestCase):
    def test_detect_todo_cluster_then_write_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = pathlib.Path(tmp) / "feature.py"
            mod.write_text("# TODO: step1\n# TODO: step2\n# TODO: step3\ndef impl(): pass\n")
            sigs = detect_resurrection_signals(
                workspace_root=tmp,
                touches=["feature.py"],
                feature_keywords=["feature"],
                repo="",
                todo_cluster_min_size=3,
            )
            self.assertTrue(len(sigs) >= 1)
            report_path = write_resurrection_report(
                feature_id="integ-test",
                signals=sigs,
                bob3_root=tmp,
            )
            self.assertTrue(pathlib.Path(report_path).exists())
            content = pathlib.Path(report_path).read_text()
            self.assertIn("todo_cluster", content)

    def test_detect_stub_then_write_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = pathlib.Path(tmp) / "service.py"
            mod.write_text("__all__ = ['init_service']\ndef init_service():\n    pass\n")
            sigs = detect_resurrection_signals(
                workspace_root=tmp,
                touches=["service.py"],
                feature_keywords=["service"],
                repo="",
            )
            stub_sigs = [s for s in sigs if s.signal_kind == "export_without_impl"]
            self.assertTrue(len(stub_sigs) >= 1)
            report_path = write_resurrection_report(
                feature_id="integ-stub",
                signals=stub_sigs,
                bob3_root=tmp,
            )
            content = pathlib.Path(report_path).read_text()
            self.assertIn("export_without_impl", content)
            self.assertIn("finish_stub", content)


if __name__ == "__main__":
    unittest.main()
