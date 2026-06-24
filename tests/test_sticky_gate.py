"""Tests for bob.sticky_gate module — sticky-completed gate integration."""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob.sticky_gate import prevent_completed_regression


def test_prevent_completed_regression_blocks_demotion_when_parent_completed_and_acs_verify():
    """prevent_completed_regression blocks demotion when parent_completed=True and AC file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "feature.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Feature implementation\n")

        criteria = ["File exists: src/feature.py", "Function defined: feature.run"]

        result = prevent_completed_regression(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is True, "Should block demotion when parent_completed=True and AC file exists"


def test_prevent_completed_regression_allows_demotion_when_parent_completed_false():
    """prevent_completed_regression allows demotion when parent_completed=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "feature.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Feature implementation\n")

        criteria = ["File exists: src/feature.py"]

        result = prevent_completed_regression(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when parent_completed=False"


def test_prevent_completed_regression_allows_demotion_when_ac_file_missing():
    """prevent_completed_regression allows demotion when AC file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)

        criteria = ["File exists: src/feature.py"]

        result = prevent_completed_regression(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when AC file is missing"


def test_prevent_completed_regression_allows_promotion_to_ready():
    """prevent_completed_regression does not block transition to 'ready'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "feature.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Feature implementation\n")

        criteria = ["File exists: src/feature.py"]

        result = prevent_completed_regression(
            parent_completed=True,
            target_status="ready",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should not block transition to 'ready' status"


def test_prevent_completed_regression_handles_json_criteria():
    """prevent_completed_regression parses JSON-formatted acceptance criteria."""
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "module.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Module\n")

        criteria_json = json.dumps(["File exists: src/module.py", "pytest: tests/test_module.py"])

        result = prevent_completed_regression(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria_json,
            workspace=ws,
        )

        assert result is True, "Should parse JSON criteria and block demotion"


def test_prevent_completed_regression_ignores_non_file_acs():
    """prevent_completed_regression only checks file-existence ACs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)

        criteria = ["Function defined: module.run", "pytest: tests/test_module.py"]

        result = prevent_completed_regression(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when no file-existence ACs present"


def test_prevent_completed_regression_with_multiple_ac_files():
    """prevent_completed_regression blocks only when ALL AC files exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)

        file1 = ws / "src" / "module1.py"
        file1.parent.mkdir(parents=True, exist_ok=True)
        file1.write_text("# Module 1\n")
        # file2 intentionally missing

        criteria = ["File exists: src/module1.py", "File exists: src/module2.py"]

        result = prevent_completed_regression(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when any AC file is missing"


def test_prevent_completed_regression_invalid_parent_completed_raises():
    """prevent_completed_regression raises ValueError for non-bool parent_completed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        with pytest.raises(ValueError, match="parent_completed"):
            prevent_completed_regression(
                parent_completed="yes",  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=ws,
            )


def test_prevent_completed_regression_invalid_target_status_raises():
    """prevent_completed_regression raises ValueError for empty target_status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        with pytest.raises(ValueError, match="target_status"):
            prevent_completed_regression(
                parent_completed=True,
                target_status="",
                acceptance_criteria=None,
                workspace=ws,
            )


def test_evaluate_with_sticky_completion_blocks_demotion_when_parent_completed_and_acs_verify():
    """Gate blocks demotion when parent_completed=True and file-existence ACs still pass."""
    from bob77.sticky_gate import evaluate_with_sticky_completion

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        # Create the file mentioned in AC
        ac_file = ws / "src" / "feature.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Feature implementation\n")

        criteria = ["File exists: src/feature.py", "Function defined: feature.run"]

        result = evaluate_with_sticky_completion(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is True, "Should block demotion when parent_completed=True and AC file exists"


def test_evaluate_with_sticky_completion_allows_demotion_when_parent_completed_false():
    """Gate allows demotion when parent_completed=False regardless of AC state."""
    from bob77.sticky_gate import evaluate_with_sticky_completion

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "feature.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Feature implementation\n")

        criteria = ["File exists: src/feature.py"]

        result = evaluate_with_sticky_completion(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when parent_completed=False"


def test_evaluate_with_sticky_completion_allows_demotion_when_ac_file_missing():
    """Gate allows demotion when AC file is missing even if parent_completed=True."""
    from bob77.sticky_gate import evaluate_with_sticky_completion

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        # AC file intentionally NOT created

        criteria = ["File exists: src/feature.py"]

        result = evaluate_with_sticky_completion(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when AC file is missing"


def test_evaluate_with_sticky_completion_allows_promotion_to_ready():
    """Gate does not block promotion to 'ready' or other non-demoting statuses."""
    from bob77.sticky_gate import evaluate_with_sticky_completion

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "feature.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Feature implementation\n")

        criteria = ["File exists: src/feature.py"]

        result = evaluate_with_sticky_completion(
            parent_completed=True,
            target_status="ready",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should not block transition to 'ready' status"


def test_evaluate_with_sticky_completion_handles_json_criteria():
    """Function parses JSON-formatted acceptance criteria correctly."""
    from bob77.sticky_gate import evaluate_with_sticky_completion
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)
        ac_file = ws / "src" / "module.py"
        ac_file.parent.mkdir(parents=True, exist_ok=True)
        ac_file.write_text("# Module\n")

        criteria_json = json.dumps(["File exists: src/module.py", "pytest: tests/test_module.py"])

        result = evaluate_with_sticky_completion(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria_json,
            workspace=ws,
        )

        assert result is True, "Should parse JSON criteria and block demotion"


def test_evaluate_with_sticky_completion_ignores_non_file_acs():
    """Gate only checks file-existence ACs, ignores function/class/pytest ACs."""
    from bob77.sticky_gate import evaluate_with_sticky_completion

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)

        # Only non-file ACs
        criteria = ["Function defined: module.run", "pytest: tests/test_module.py"]

        result = evaluate_with_sticky_completion(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when no file-existence ACs present"


def test_evaluate_with_sticky_completion_with_multiple_ac_files():
    """Gate blocks only when ALL AC files exist."""
    from bob77.sticky_gate import evaluate_with_sticky_completion

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = pathlib.Path(tmpdir)

        # Create only one of two AC files
        file1 = ws / "src" / "module1.py"
        file1.parent.mkdir(parents=True, exist_ok=True)
        file1.write_text("# Module 1\n")
        # file2 intentionally missing

        criteria = ["File exists: src/module1.py", "File exists: src/module2.py"]

        result = evaluate_with_sticky_completion(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=criteria,
            workspace=ws,
        )

        assert result is False, "Should allow demotion when any AC file is missing"
