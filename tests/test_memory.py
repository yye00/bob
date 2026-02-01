"""
Tests for Project Memory System
================================

Tests the memory module's test stability tracking, recipe management,
and integration hooks. Semantic memory (Mem0) tests are skipped if
no API key is available.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.orchestrator.memory import (
    ProjectMemory,
    _hash_error_signature,
    _compute_impl_hash,
    _MEM0_AVAILABLE,
    _STABILITY_FAILURE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    (project_dir / ".bob").mkdir()
    return project_dir


@pytest.fixture
def memory(temp_project_dir):
    """Create a ProjectMemory with Mem0 disabled (no API key needed)."""
    # Force Mem0 off by patching _MEM0_AVAILABLE
    with patch("bob.orchestrator.memory._MEM0_AVAILABLE", False):
        mem = ProjectMemory(temp_project_dir, "test-project-123")
    return mem


@pytest.fixture
def mock_task():
    """Create a mock task for testing."""
    task = MagicMock()
    task.spec_id = "T001"
    task.title = "Build MPO constructor"
    task.description = "Implement the MPO W-matrix builder for Heisenberg model"
    task.depends_on = ["T000"]
    task.expected_outputs = []
    task.verify_script = "python -m pytest tests/"
    return task


# ---------------------------------------------------------------------------
# Error Signature Hashing
# ---------------------------------------------------------------------------


class TestErrorSignatureHashing:
    def test_same_error_same_hash(self):
        """Same logical error with different paths/lines gets same hash."""
        err1 = "File /home/user/project/foo.py, line 42, in bar\nValueError: bad value"
        err2 = "File /tmp/other/foo.py, line 99, in bar\nValueError: bad value"
        assert _hash_error_signature(err1) == _hash_error_signature(err2)

    def test_different_errors_different_hash(self):
        """Genuinely different errors get different hashes."""
        err1 = "ValueError: bad value"
        err2 = "TypeError: not a number"
        assert _hash_error_signature(err1) != _hash_error_signature(err2)

    def test_timestamps_normalized(self):
        """Timestamps are stripped from error signatures."""
        err1 = "2026-01-31T11:17:00 Error: something broke"
        err2 = "2026-02-01T15:30:00 Error: something broke"
        assert _hash_error_signature(err1) == _hash_error_signature(err2)

    def test_hex_addresses_normalized(self):
        """Hex addresses are normalized."""
        err1 = "Object at 0xDEADBEEF crashed"
        err2 = "Object at 0xCAFEBABE crashed"
        assert _hash_error_signature(err1) == _hash_error_signature(err2)


# ---------------------------------------------------------------------------
# Test Stability Tracking
# ---------------------------------------------------------------------------


class TestTestStability:
    def test_record_single_result(self, memory):
        """Can record a single test result."""
        memory.record_test_result(
            test_name="test_mpo_shape",
            task_id="T002",
            passed=True,
        )

        stability = memory._load_test_stability()
        assert "test_mpo_shape" in stability
        assert len(stability["test_mpo_shape"]["results"]) == 1
        assert stability["test_mpo_shape"]["results"][0]["passed"] is True

    def test_multiple_results_tracked(self, memory):
        """Multiple results for same test are tracked."""
        for i in range(5):
            memory.record_test_result(
                test_name="test_contraction",
                task_id="T005",
                passed=False,
                error="einsum subscript error",
                impl_hash=f"impl_{i}",
            )

        stability = memory._load_test_stability()
        assert len(stability["test_contraction"]["results"]) == 5

    def test_suspect_buggy_detection(self, memory):
        """Same error across multiple independent impls = suspect buggy."""
        for i in range(_STABILITY_FAILURE_THRESHOLD):
            memory.record_test_result(
                test_name="test_einsum_contract",
                task_id="T009",
                passed=False,
                error="ValueError: einsum subscript 'S' is not valid",
                impl_hash=f"independent_impl_{i}",
            )

        suspects = memory.get_suspect_tests()
        assert len(suspects) == 1
        assert suspects[0]["test_name"] == "test_einsum_contract"
        assert suspects[0]["task_id"] == "T009"

    def test_suspect_buggy_filter_by_task(self, memory):
        """Can filter suspect tests by task ID."""
        # Add suspect for T009
        for i in range(_STABILITY_FAILURE_THRESHOLD):
            memory.record_test_result(
                test_name="test_a",
                task_id="T009",
                passed=False,
                error="error A",
                impl_hash=f"impl_{i}",
            )
        # Add suspect for T005
        for i in range(_STABILITY_FAILURE_THRESHOLD):
            memory.record_test_result(
                test_name="test_b",
                task_id="T005",
                passed=False,
                error="error B",
                impl_hash=f"impl_{i}",
            )

        suspects_t009 = memory.get_suspect_tests(task_id="T009")
        assert len(suspects_t009) == 1
        assert suspects_t009[0]["test_name"] == "test_a"

        suspects_t005 = memory.get_suspect_tests(task_id="T005")
        assert len(suspects_t005) == 1
        assert suspects_t005[0]["test_name"] == "test_b"

    def test_stable_test_not_flagged(self, memory):
        """Test that passes consistently is not flagged."""
        for i in range(5):
            memory.record_test_result(
                test_name="test_working",
                task_id="T001",
                passed=True,
            )

        suspects = memory.get_suspect_tests()
        assert len(suspects) == 0

    def test_different_errors_not_flagged(self, memory):
        """Different errors across impls = not suspect (might be real bugs)."""
        errors = [
            "ValueError: shape mismatch",
            "TypeError: not a tensor",
            "IndexError: out of range",
        ]
        for i, err in enumerate(errors):
            memory.record_test_result(
                test_name="test_varied",
                task_id="T003",
                passed=False,
                error=err,
                impl_hash=f"impl_{i}",
            )

        suspects = memory.get_suspect_tests()
        assert len(suspects) == 0

    def test_results_bounded(self, memory):
        """Results list is bounded to prevent unbounded growth."""
        for i in range(30):
            memory.record_test_result(
                test_name="test_many",
                task_id="T001",
                passed=(i % 2 == 0),
            )

        stability = memory._load_test_stability()
        assert len(stability["test_many"]["results"]) <= 20


# ---------------------------------------------------------------------------
# Recipe Management
# ---------------------------------------------------------------------------


class TestRecipes:
    def test_save_and_load_recipe(self, memory):
        """Can save and retrieve a recipe."""
        memory.save_recipe(
            task_id="T002",
            title="Heisenberg MPO Construction",
            pattern="W-matrix with bond_dim=5",
            key_code="W = np.zeros((5, 5, 2, 2))",
            dependencies=["T001"],
        )

        recipes = memory._load_recipes()
        assert "T002" in recipes
        assert recipes["T002"]["title"] == "Heisenberg MPO Construction"
        assert recipes["T002"]["key_code"] == "W = np.zeros((5, 5, 2, 2))"

    def test_get_relevant_recipes(self, memory):
        """Recipes from dependency tasks are returned."""
        memory.save_recipe(
            task_id="T001",
            title="Tensor utilities",
            pattern="Index contraction helpers",
        )
        memory.save_recipe(
            task_id="T002",
            title="MPO builder",
            pattern="W-matrix construction",
        )

        relevant = memory.get_relevant_recipes("T003", depends_on=["T001", "T002"])
        assert len(relevant) == 2

        titles = {r["title"] for r in relevant}
        assert "Tensor utilities" in titles
        assert "MPO builder" in titles

    def test_no_recipes_for_unrelated_deps(self, memory):
        """No recipes returned for tasks with no saved recipes."""
        memory.save_recipe(
            task_id="T001",
            title="Something",
            pattern="Something",
        )

        relevant = memory.get_relevant_recipes("T005", depends_on=["T004"])
        assert len(relevant) == 0


# ---------------------------------------------------------------------------
# Retrieve (Prompt Injection)
# ---------------------------------------------------------------------------


class TestRetrieve:
    def test_retrieve_empty_when_no_data(self, memory, mock_task):
        """Retrieve returns empty string when no memories exist."""
        result = memory.retrieve(mock_task)
        assert result == ""

    def test_retrieve_includes_suspect_tests(self, memory, mock_task):
        """Retrieve includes suspect test warnings."""
        # Create a suspect test for this task
        for i in range(_STABILITY_FAILURE_THRESHOLD):
            memory.record_test_result(
                test_name="test_broken",
                task_id="T001",
                passed=False,
                error="always fails",
                impl_hash=f"impl_{i}",
            )

        result = memory.retrieve(mock_task)
        assert "Suspect Tests" in result
        assert "test_broken" in result

    def test_retrieve_includes_recipes(self, memory, mock_task):
        """Retrieve includes recipes from dependency tasks."""
        memory.save_recipe(
            task_id="T000",
            title="Base utilities",
            pattern="Tensor helpers",
            key_code="def contract(a, b): ...",
        )

        result = memory.retrieve(mock_task)
        assert "Working Patterns" in result
        assert "Base utilities" in result

    def test_retrieve_truncates_long_output(self, memory, mock_task):
        """Retrieve respects the character limit."""
        # Add many recipes to exceed limit
        for i in range(50):
            dep_id = f"T000_{i}"
            memory.save_recipe(
                task_id=dep_id,
                title=f"Recipe {i} with a very long title that takes up space " * 3,
                pattern="A" * 500,
                key_code="code " * 100,
            )
            mock_task.depends_on = [f"T000_{j}" for j in range(50)]

        result = memory.retrieve(mock_task)
        assert len(result) <= 7000  # Some buffer above _MAX_PROMPT_CHARS


# ---------------------------------------------------------------------------
# Extract (Post-verification)
# ---------------------------------------------------------------------------


class TestExtract:
    @pytest.mark.asyncio
    async def test_extract_on_success(self, memory, mock_task):
        """Extract saves recipe on success."""
        result = await memory.extract(
            task=mock_task,
            verification_passed=True,
            verification_msg="All tests passed",
            attempt_number=1,
        )

        assert result["recipe_saved"] is True

        recipes = memory._load_recipes()
        assert "T001" in recipes

    @pytest.mark.asyncio
    async def test_extract_records_test_results(self, memory, mock_task):
        """Extract records individual test results."""
        test_results = [
            {"name": "test_shape", "passed": True},
            {"name": "test_values", "passed": False, "error": "AssertionError"},
        ]

        result = await memory.extract(
            task=mock_task,
            verification_passed=False,
            verification_msg="1 test failed",
            attempt_number=1,
            test_results=test_results,
        )

        assert result["test_results_recorded"] == 2

        stability = memory._load_test_stability()
        assert "test_shape" in stability
        assert "test_values" in stability

    @pytest.mark.asyncio
    async def test_extract_complexity_scaling(self, memory, mock_task):
        """Complexity increases with attempt number."""
        # First attempt — low complexity
        await memory.extract(
            task=mock_task,
            verification_passed=False,
            verification_msg="Failed",
            attempt_number=1,
        )

        # Tenth attempt — high complexity
        await memory.extract(
            task=mock_task,
            verification_passed=True,
            verification_msg="Passed",
            attempt_number=10,
        )

        # Check recipe was saved with high-attempt marker
        recipes = memory._load_recipes()
        assert "T001" in recipes


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_with_no_data(self, memory):
        """Stats work with empty memory."""
        stats = memory.get_stats()
        assert stats["semantic_memories"] == 0
        assert stats["test_stability_entries"] == 0
        assert stats["suspect_tests"] == 0
        assert stats["recipes"] == 0

    def test_stats_with_data(self, memory):
        """Stats reflect actual data."""
        memory.record_test_result("test_a", "T001", True)
        memory.record_test_result("test_b", "T002", False, "error")
        memory.save_recipe("T001", "Recipe 1", "Pattern")

        stats = memory.get_stats()
        assert stats["test_stability_entries"] == 2
        assert stats["recipes"] == 1


# ---------------------------------------------------------------------------
# Impl Hash
# ---------------------------------------------------------------------------


class TestImplHash:
    def test_different_content_different_hash(self, temp_project_dir):
        """Different file content produces different hashes."""
        task = MagicMock()
        output1 = MagicMock()
        output1.path = "file1.py"
        output2 = MagicMock()
        output2.path = "file1.py"
        task.expected_outputs = [output1]

        (temp_project_dir / "file1.py").write_text("version 1")
        hash1 = _compute_impl_hash(task, temp_project_dir)

        (temp_project_dir / "file1.py").write_text("version 2")
        hash2 = _compute_impl_hash(task, temp_project_dir)

        assert hash1 != hash2

    def test_no_files_returns_hash(self, temp_project_dir):
        """Missing files still produce a deterministic hash."""
        task = MagicMock()
        output = MagicMock()
        output.path = "nonexistent.py"
        task.expected_outputs = [output]

        h = _compute_impl_hash(task, temp_project_dir)
        assert isinstance(h, str)
        assert len(h) == 16
