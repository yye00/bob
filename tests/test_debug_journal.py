"""Tests for debug journal diff-aware debugging functionality."""

import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from bob.orchestrator.debug_journal import DebugJournal
from bob.models.base import ExpectedOutput, Task


class TestDebugJournal:
    """Test suite for DebugJournal diff-aware debugging features."""
    
    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.journal = DebugJournal(self.temp_dir)
        
        # Create a mock task with expected outputs
        self.task = Mock(spec=Task)
        self.task.spec_id = "TEST001"
        self.task.title = "Test Task"
        self.task.expected_outputs = [
            ExpectedOutput(path="test_file.py"),
            ExpectedOutput(path="config.json"),
        ]
        
    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)
    
    def test_record_file_snapshot_new_files(self):
        """Test recording file snapshots for newly created files."""
        # Create test files
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("""def hello():
    print("Hello, world!")
    return "hello"

class TestClass:
    def method(self):
        pass
""")
        
        config_file = self.temp_dir / "config.json"
        config_file.write_text('{"debug": true, "version": "1.0"}')
        
        # Record snapshot
        self.journal.record_file_snapshot(self.task)
        
        # Check that snapshots were recorded
        assert self.task.spec_id in self.journal._snapshots
        snapshot = self.journal._snapshots[self.task.spec_id][0]
        
        # Check test_file.py snapshot (should be full content since < 100 lines)
        assert "test_file.py" in snapshot
        file_snap = snapshot["test_file.py"]
        assert file_snap["type"] == "full"
        assert "def hello():" in file_snap["content"]
        assert "class TestClass:" in file_snap["content"]
        assert file_snap["lines"] == 8  # Includes empty line at end
        assert "hash" in file_snap
        
        # Check config.json snapshot
        assert "config.json" in snapshot
        config_snap = snapshot["config.json"]
        assert config_snap["type"] == "full"
        assert '"debug": true' in config_snap["content"]
    
    def test_record_file_snapshot_missing_files(self):
        """Test recording snapshots when expected files don't exist."""
        # Don't create any files
        self.journal.record_file_snapshot(self.task)
        
        snapshot = self.journal._snapshots[self.task.spec_id][0]
        
        # Both files should be marked as missing
        assert snapshot["test_file.py"]["type"] == "missing"
        assert not snapshot["test_file.py"]["exists"]
        assert snapshot["config.json"]["type"] == "missing"
        assert not snapshot["config.json"]["exists"]
    
    def test_record_file_snapshot_large_files(self):
        """Test snapshot behavior for large files (>100 lines)."""
        # Create a large file
        large_content = []
        large_content.append("import os")
        large_content.append("import sys")
        for i in range(120):
            if i % 20 == 0:
                large_content.append(f"def function_{i}():")
                large_content.append(f"    '''Function {i}'''")
                large_content.append(f"    return {i}")
            elif i % 15 == 0:
                large_content.append(f"class Class_{i}:")
                large_content.append(f"    '''Class {i}'''")
                large_content.append("    pass")
            else:
                large_content.append(f"# Line {i}")
        
        large_file = self.temp_dir / "test_file.py"
        large_file.write_text("\n".join(large_content))
        
        # Record snapshot
        self.journal.record_file_snapshot(self.task)
        
        snapshot = self.journal._snapshots[self.task.spec_id][0]
        file_snap = snapshot["test_file.py"]
        
        # Should use summary mode for large files
        assert file_snap["type"] == "summary"
        assert file_snap["lines"] > 100
        assert "key_lines" in file_snap
        
        # Check that key lines were extracted
        key_lines = file_snap["key_lines"]
        assert len(key_lines["functions"]) > 0
        assert len(key_lines["classes"]) > 0
        assert len(key_lines["imports"]) > 0
        assert any("def function_" in line for line in key_lines["functions"])
        assert any("class Class_" in line for line in key_lines["classes"])
        assert any("import" in line for line in key_lines["imports"])
    
    def test_get_diff_summary_no_changes(self):
        """Test diff summary when there are no changes."""
        # Create a file and take two identical snapshots
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("def hello(): pass")
        
        self.journal.record_file_snapshot(self.task)
        self.journal.record_file_snapshot(self.task)
        
        # Should report no changes
        diff_summary = self.journal.get_diff_summary(self.task.spec_id)
        assert diff_summary == "No file changes detected between attempts."
    
    def test_get_diff_summary_file_creation(self):
        """Test diff summary when files are created."""
        # First snapshot with no files
        self.journal.record_file_snapshot(self.task)
        
        # Create files
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("def hello(): pass")
        
        # Second snapshot with files
        self.journal.record_file_snapshot(self.task)
        
        diff_summary = self.journal.get_diff_summary(self.task.spec_id)
        assert "+ Created test_file.py (1 lines)" in diff_summary
    
    def test_get_diff_summary_file_modification(self):
        """Test diff summary when files are modified."""
        # Create initial file
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("def hello(): pass")
        self.journal.record_file_snapshot(self.task)
        
        # Modify file
        test_file.write_text("""def hello(): 
    print("Hello!")
    return "hello"

def goodbye():
    print("Goodbye!")
""")
        self.journal.record_file_snapshot(self.task)
        
        diff_summary = self.journal.get_diff_summary(self.task.spec_id)
        assert "~ Modified test_file.py (+6 lines)" in diff_summary
        
        # Should include actual diff for small files
        assert "+    print(\"Hello!\")" in diff_summary
        assert "+def goodbye():" in diff_summary
    
    def test_get_diff_summary_file_deletion(self):
        """Test diff summary when files are deleted."""
        # Create file and take snapshot
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("def hello(): pass")
        self.journal.record_file_snapshot(self.task)
        
        # Delete file and take another snapshot
        test_file.unlink()
        self.journal.record_file_snapshot(self.task)
        
        diff_summary = self.journal.get_diff_summary(self.task.spec_id)
        assert "- Deleted test_file.py" in diff_summary
    
    def test_get_failed_approaches(self):
        """Test extraction of failed approaches from journal."""
        # Record some debug attempts with approaches
        self.journal.record_attempt(
            spec_id=self.task.spec_id,
            task_title=self.task.title,
            attempt_number=1,
            verification_error="Import error",
            approach_taken="Added missing import statement",
        )
        
        self.journal.record_attempt(
            spec_id=self.task.spec_id,
            task_title=self.task.title,
            attempt_number=2,
            verification_error="Function not defined",
            approach_taken="Fixed typo in function name",
        )
        
        failed_approaches = self.journal.get_failed_approaches(self.task.spec_id)
        
        assert "× Added missing import statement" in failed_approaches
        assert "× Fixed typo in function name" in failed_approaches
    
    def test_get_failed_approaches_no_approaches(self):
        """Test get_failed_approaches when no approaches are recorded."""
        failed_approaches = self.journal.get_failed_approaches(self.task.spec_id)
        assert failed_approaches == ""
    
    def test_get_failed_approaches_deduplication(self):
        """Test that duplicate approaches are not repeated."""
        # Record same approach multiple times
        for i in range(3):
            self.journal.record_attempt(
                spec_id=self.task.spec_id,
                task_title=self.task.title,
                attempt_number=i + 1,
                verification_error="Same error",
                approach_taken="Same approach",
            )
        
        failed_approaches = self.journal.get_failed_approaches(self.task.spec_id)
        
        # Should only appear once
        assert failed_approaches.count("× Same approach") == 1
    
    def test_extract_key_lines(self):
        """Test extraction of key lines from Python code."""
        lines = [
            "import os",
            "from pathlib import Path",
            "",
            "# This is a comment",
            "def function_one():",
            "    '''Docstring'''",
            "    return 1",
            "",
            "class MyClass:",
            "    '''Class docstring'''",
            "    def method(self):",
            "        pass",
            "",
            "@property",
            "def getter(self):",
            "    return self._value",
            "",
            "# TODO: Implement this",
            "def incomplete():",
            "    # FIXME: This is broken", 
            "    pass",
        ]
        
        key_lines = self.journal._extract_key_lines(lines)
        
        # Check that different categories were detected
        assert len(key_lines["imports"]) == 2
        assert any("import os" in line for line in key_lines["imports"])
        assert any("from pathlib" in line for line in key_lines["imports"])
        
        assert len(key_lines["functions"]) >= 2
        assert any("def function_one" in line for line in key_lines["functions"])
        assert any("def getter" in line for line in key_lines["functions"])
        
        assert len(key_lines["classes"]) == 1
        assert any("class MyClass" in line for line in key_lines["classes"])
        
        assert len(key_lines["other"]) >= 1
        assert any("@property" in line for line in key_lines["other"])
        # TODO/FIXME lines should be detected
        other_lines = key_lines["other"]
        assert any("TODO" in line for line in other_lines) or len([line for line in other_lines if "TODO" in line or "FIXME" in line]) > 0
    
    def test_clear_journal_clears_snapshots(self):
        """Test that clearing a journal also clears its snapshots."""
        # Create some snapshots
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("def hello(): pass")
        self.journal.record_file_snapshot(self.task)
        
        # Verify snapshots exist
        assert self.task.spec_id in self.journal._snapshots
        
        # Clear journal
        self.journal.clear_journal(self.task.spec_id)
        
        # Verify snapshots are cleared
        assert self.task.spec_id not in self.journal._snapshots
    
    def test_thread_safety(self):
        """Test that snapshot operations are thread-safe."""
        import threading
        import time
        
        # Create test file
        test_file = self.temp_dir / "test_file.py"
        test_file.write_text("def hello(): pass")
        
        errors = []
        
        def record_snapshots():
            try:
                for i in range(10):
                    self.journal.record_file_snapshot(self.task)
                    time.sleep(0.001)  # Small delay to encourage race conditions
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=record_snapshots)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have no errors
        assert len(errors) == 0
        
        # Should have snapshots from all threads
        assert self.task.spec_id in self.journal._snapshots
        snapshots = self.journal._snapshots[self.task.spec_id]
        assert len(snapshots) > 0