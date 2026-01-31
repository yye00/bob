"""
Debug Journal — MemGPT-style Retrieval for Debug Context
=========================================================

Instead of stuffing the full debug history into every prompt (which eats
the context window and puts Claude in the "dumb zone"), we:

1. Store full debug history on disk at .bob/debug/<task_id>.md
2. Inject only a compact summary into the debug prompt (~200 tokens)
3. Tell Claude where the journal is so it can read it on-demand via tools
4. Track file snapshots between debug attempts to show what changed
5. Generate diff summaries to prevent repeating failed approaches

This keeps the working context lean while giving Claude full access to
debug history and diff context through its file-read tools.
"""

import difflib
import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class DebugJournal:
    """Manages per-task debug journals on disk.
    
    Each task gets a markdown file at .bob/debug/<spec_id>.md containing
    a structured log of every debug attempt, error, and what was tried.
    
    The journal is designed to be:
    - Human-readable (markdown)
    - Machine-parseable (structured sections)
    - Claude-readable (can be cat'd by Claude Code tools)
    - Compact in summary form (1-line per attempt for prompt injection)
    """
    
    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.debug_dir = self.project_dir / ".bob" / "debug"
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        # Per-task locks for concurrent access (parallel execution)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # Protects _locks dict itself
        # File snapshots for diff tracking
        self._snapshots: dict[str, dict[str, dict]] = {}  # spec_id -> attempt_num -> file_snapshots

    def _get_lock(self, spec_id: str) -> threading.Lock:
        """Get or create a lock for a specific task's journal."""
        with self._locks_lock:
            if spec_id not in self._locks:
                self._locks[spec_id] = threading.Lock()
            return self._locks[spec_id]
    
    def journal_path(self, spec_id: str) -> Path:
        """Get the path to a task's debug journal."""
        # Sanitize spec_id for filename
        safe_id = spec_id.replace("/", "_").replace("\\", "_")
        return self.debug_dir / f"{safe_id}.md"
    
    def has_journal(self, spec_id: str) -> bool:
        """Check if a task has a debug journal."""
        return self.journal_path(spec_id).exists()
    
    def get_attempt_count(self, spec_id: str) -> int:
        """Get the number of debug attempts recorded for a task."""
        path = self.journal_path(spec_id)
        if not path.exists():
            return 0
        content = path.read_text()
        return content.count("## Debug Attempt")

    def record_file_snapshot(self, task) -> None:
        """Record snapshots of files for diff tracking.
        
        Takes snapshots of all expected output files before a debug attempt.
        Stores file contents (for small files) or hashes + key lines (for large files).
        Thread-safe using per-task locks.
        
        Args:
            task: Task object with expected_outputs list
        """
        spec_id = task.spec_id
        lock = self._get_lock(spec_id)
        
        with lock:
            if spec_id not in self._snapshots:
                self._snapshots[spec_id] = {}
            
            # Use the next available attempt number (length of current snapshots)
            attempt_num = len(self._snapshots[spec_id])
            snapshot = {}
            
            for output in task.expected_outputs:
                file_path = self.project_dir / output.path
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        lines = content.split('\n')
                        
                        # For small files (< 100 lines), store full content
                        # For large files, store hash + key lines (functions, classes, etc.)
                        if len(lines) <= 100:
                            snapshot[output.path] = {
                                'type': 'full',
                                'content': content,
                                'lines': len(lines),
                                'hash': hashlib.md5(content.encode()).hexdigest()[:8],
                                'exists': True
                            }
                        else:
                            # Extract key lines for large files
                            key_lines = self._extract_key_lines(lines)
                            snapshot[output.path] = {
                                'type': 'summary',
                                'key_lines': key_lines,
                                'lines': len(lines),
                                'hash': hashlib.md5(content.encode()).hexdigest()[:8],
                                'exists': True
                            }
                    except Exception as e:
                        # File exists but can't be read (binary, permission, etc.)
                        snapshot[output.path] = {
                            'type': 'error',
                            'error': str(e),
                            'exists': True
                        }
                else:
                    snapshot[output.path] = {
                        'type': 'missing',
                        'exists': False
                    }
            
            self._snapshots[spec_id][attempt_num] = snapshot

    def _extract_key_lines(self, lines: list[str]) -> dict[str, list[str]]:
        """Extract key lines from a file for compact diff tracking.
        
        Identifies function definitions, class definitions, imports,
        and other structural elements that are most relevant for debugging.
        """
        key_lines = {
            'functions': [],
            'classes': [],
            'imports': [],
            'other': []
        }
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            
            # Check for TODO/FIXME first (even in comments)
            if any(keyword in stripped for keyword in ['TODO', 'FIXME', 'XXX', 'HACK']):
                key_lines['other'].append(f"{i+1}: {stripped}")
                continue
                
            # Skip other comments
            if stripped.startswith('#'):
                continue
                
            # Python patterns
            if stripped.startswith('def '):
                key_lines['functions'].append(f"{i+1}: {stripped}")
            elif stripped.startswith('class '):
                key_lines['classes'].append(f"{i+1}: {stripped}")
            elif stripped.startswith(('import ', 'from ')) and 'import' in stripped:
                key_lines['imports'].append(f"{i+1}: {stripped}")
            elif stripped.startswith('@'):  # Decorators
                key_lines['other'].append(f"{i+1}: {stripped}")
                
        return key_lines

    def get_diff_summary(self, spec_id: str, max_lines: int = 50) -> str:
        """Get a human-readable diff between the last two attempts.
        
        Compares file snapshots from the previous attempt with the current one
        to show what changed. Keeps output compact for prompt injection.
        
        Args:
            spec_id: Task spec ID
            max_lines: Maximum lines in the diff summary
            
        Returns:
            Human-readable diff summary, or empty string if no changes/attempts
        """
        lock = self._get_lock(spec_id)
        
        with lock:
            if spec_id not in self._snapshots:
                return ""
            
            snapshots = self._snapshots[spec_id]
            attempt_nums = sorted(snapshots.keys())
            
            if len(attempt_nums) < 2:
                return ""
            
            # Get the last two attempts
            prev_attempt = attempt_nums[-2]
            current_attempt = attempt_nums[-1]
            
            prev_snap = snapshots[prev_attempt]
            current_snap = snapshots[current_attempt]
            
            changes = []
            all_files = set(prev_snap.keys()) | set(current_snap.keys())
            
            for file_path in sorted(all_files):
                prev_info = prev_snap.get(file_path, {'type': 'missing', 'exists': False})
                current_info = current_snap.get(file_path, {'type': 'missing', 'exists': False})
                
                # File creation/deletion
                if not prev_info['exists'] and current_info['exists']:
                    changes.append(f"+ Created {file_path} ({current_info.get('lines', 0)} lines)")
                    continue
                elif prev_info['exists'] and not current_info['exists']:
                    changes.append(f"- Deleted {file_path}")
                    continue
                elif not prev_info['exists'] and not current_info['exists']:
                    continue  # Both missing, no change
                
                # File modification detection
                prev_hash = prev_info.get('hash', '')
                current_hash = current_info.get('hash', '')
                
                if prev_hash == current_hash:
                    continue  # No changes
                
                # Show line count change
                prev_lines = prev_info.get('lines', 0)
                current_lines = current_info.get('lines', 0)
                line_diff = current_lines - prev_lines
                
                if line_diff > 0:
                    changes.append(f"~ Modified {file_path} (+{line_diff} lines)")
                elif line_diff < 0:
                    changes.append(f"~ Modified {file_path} ({line_diff} lines)")
                else:
                    changes.append(f"~ Modified {file_path} (same line count)")
                
                # For full content files, show actual diff
                if (prev_info.get('type') == 'full' and 
                    current_info.get('type') == 'full' and 
                    len(changes) < max_lines // 3):  # Leave room for other files
                    
                    prev_content = prev_info.get('content', '').split('\n')
                    current_content = current_info.get('content', '').split('\n')
                    
                    diff_lines = list(difflib.unified_diff(
                        prev_content, current_content,
                        fromfile=f"{file_path} (attempt {prev_attempt})",
                        tofile=f"{file_path} (attempt {current_attempt})",
                        lineterm='', n=2
                    ))
                    
                    if diff_lines:
                        # Skip header lines and show just the changes
                        relevant_diff = [line for line in diff_lines[2:] 
                                       if line.startswith(('+', '-')) and 
                                       not line.startswith(('+++', '---'))]
                        
                        if relevant_diff and len(relevant_diff) <= 10:  # Show small diffs
                            changes.append("  " + "\n  ".join(relevant_diff[:10]))
            
            if not changes:
                return "No file changes detected between attempts."
            
            # Truncate if too long
            if len(changes) > max_lines:
                changes = changes[:max_lines]
                changes.append(f"... ({len(all_files) - max_lines} more files changed)")
            
            return "\n".join(changes)

    def get_failed_approaches(self, spec_id: str, max_approaches: int = 5) -> str:
        """Get a summary of approaches that failed in previous attempts.
        
        Extracts approach descriptions from previous journal entries
        to help Claude avoid repeating the same failed attempts.
        
        Returns:
            Formatted list of failed approaches, or empty string if none
        """
        path = self.journal_path(spec_id)
        if not path.exists():
            return ""
        
        content = path.read_text()
        approaches = []
        
        # Extract approach lines from journal entries
        for line in content.split('\n'):
            if line.startswith('**Approach:**'):
                approach = line.replace('**Approach:**', '').strip()
                if approach and approach not in approaches:
                    approaches.append(approach)
        
        if not approaches:
            return ""
        
        # Truncate if too many
        if len(approaches) > max_approaches:
            approaches = approaches[:max_approaches]
            
        return "\n".join(f"  × {approach}" for approach in approaches)
    
    def record_attempt(
        self,
        spec_id: str,
        task_title: str,
        attempt_number: int,
        verification_error: str,
        files_modified: list[str] | None = None,
        approach_taken: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Record a debug attempt in the journal.
        
        Thread-safe: uses per-task locks for parallel execution.
        
        Args:
            spec_id: Task spec ID
            task_title: Human-readable task title
            attempt_number: Which debug attempt (1-indexed)
            verification_error: The full verification error output
            files_modified: List of files that were modified during this attempt
            approach_taken: Brief description of what was tried (optional)
            error_summary: 1-line summary of the error (optional, auto-generated if not provided)
        """
        path = self.journal_path(spec_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Auto-generate summary if not provided
        if not error_summary:
            error_summary = self._auto_summarize_error(verification_error)
        
        lock = self._get_lock(spec_id)
        with lock:
            # Create or append to journal
            if not path.exists():
                header = f"""# Debug Journal: {task_title} ({spec_id})

Created: {timestamp}
Status: IN PROGRESS

---

"""
                path.write_text(header)
            
            # Build attempt entry
            entry = f"""## Debug Attempt {attempt_number} — {timestamp}

**Summary:** {error_summary}

"""
            if approach_taken:
                entry += f"**Approach:** {approach_taken}\n\n"
            
            if files_modified:
                entry += "**Files modified:**\n"
                for f in files_modified:
                    entry += f"- `{f}`\n"
                entry += "\n"
            
            entry += f"""**Verification error (full):**
```
{verification_error.strip()}
```

---

"""
            
            # Append to journal
            with open(path, "a") as f:
                f.write(entry)
    
    def record_success(self, spec_id: str, attempt_number: int) -> None:
        """Record that debugging succeeded. Thread-safe."""
        path = self.journal_path(spec_id)
        if not path.exists():
            return
        
        lock = self._get_lock(spec_id)
        with lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Update status in header
            content = path.read_text()
            content = content.replace("Status: IN PROGRESS", f"Status: RESOLVED (attempt {attempt_number})")
            
            # Append success entry
            content += f"""## ✅ RESOLVED — {timestamp}

Task passed verification after {attempt_number} debug attempt(s).

"""
            path.write_text(content)
    
    def get_compact_summary(self, spec_id: str, max_attempts: int = 10) -> str:
        """Get a compact summary of debug history for prompt injection.
        
        Returns a brief summary (~200 tokens max) listing each attempt
        with a 1-line description. This is what goes INTO the prompt.
        Full details are in the journal file (Claude can read it).
        
        Args:
            spec_id: Task spec ID
            max_attempts: Maximum number of attempts to summarize
            
        Returns:
            Compact summary string for prompt injection
        """
        path = self.journal_path(spec_id)
        if not path.exists():
            return ""
        
        content = path.read_text()
        
        # Extract summaries from each attempt
        summaries = []
        for line in content.split("\n"):
            if line.startswith("**Summary:**"):
                summary = line.replace("**Summary:**", "").strip()
                summaries.append(summary)
        
        if not summaries:
            return ""
        
        # Truncate if too many
        if len(summaries) > max_attempts:
            summaries = summaries[-max_attempts:]
        
        # Build compact summary
        lines = [f"Previous debug attempts ({len(summaries)} total):"]
        for i, s in enumerate(summaries, 1):
            lines.append(f"  {i}. {s}")
        
        rel_path = os.path.relpath(path, self.project_dir)
        lines.append(f"\nFull debug journal: `{rel_path}` (read it for detailed error traces)")
        
        return "\n".join(lines)
    
    def get_full_journal(self, spec_id: str) -> str:
        """Get the full journal content (for display/export)."""
        path = self.journal_path(spec_id)
        if not path.exists():
            return ""
        return path.read_text()
    
    def clear_journal(self, spec_id: str) -> None:
        """Remove a specific task's debug journal. Thread-safe."""
        lock = self._get_lock(spec_id)
        with lock:
            path = self.journal_path(spec_id)
            if path.exists():
                path.unlink()
            # Also clear snapshots from memory
            if spec_id in self._snapshots:
                del self._snapshots[spec_id]
    
    def list_journals(self) -> list[dict]:
        """List all debug journals with basic info."""
        journals = []
        for path in sorted(self.debug_dir.glob("*.md")):
            content = path.read_text()
            attempt_count = content.count("## Debug Attempt")
            resolved = "RESOLVED" in content
            spec_id = path.stem
            size_kb = path.stat().st_size / 1024
            journals.append({
                "spec_id": spec_id,
                "attempts": attempt_count,
                "resolved": resolved,
                "path": str(path),
                "size_kb": round(size_kb, 1),
            })
        return journals

    def cleanup_resolved(self) -> list[str]:
        """Remove journals for tasks that were resolved. Thread-safe.
        
        Uses per-task locks so parallel tasks can't have their journals
        deleted mid-write. Only deletes journals marked RESOLVED.
        
        Returns list of spec_ids that were cleaned up.
        """
        cleaned = []
        # Snapshot the list first, then lock-per-task to delete
        paths = list(self.debug_dir.glob("*.md"))
        for path in paths:
            spec_id = path.stem
            lock = self._get_lock(spec_id)
            with lock:
                if path.exists():
                    try:
                        content = path.read_text()
                        if "RESOLVED" in content:
                            path.unlink()
                            cleaned.append(spec_id)
                    except (OSError, IOError):
                        pass  # File may have been deleted by another thread
        return cleaned

    def cleanup_all(self) -> int:
        """Remove all debug journals. Thread-safe.
        
        WARNING: Only use when no tasks are actively running.
        Uses per-task locks but can't prevent a new journal from being
        created after deletion.
        
        Returns count of files removed.
        """
        count = 0
        paths = list(self.debug_dir.glob("*.md"))
        for path in paths:
            spec_id = path.stem
            lock = self._get_lock(spec_id)
            with lock:
                if path.exists():
                    try:
                        path.unlink()
                        count += 1
                    except (OSError, IOError):
                        pass
        return count

    def total_size_kb(self) -> float:
        """Get total size of all debug journals in KB."""
        total = sum(p.stat().st_size for p in self.debug_dir.glob("*.md"))
        return round(total / 1024, 1)
    
    @staticmethod
    def _auto_summarize_error(error_text: str) -> str:
        """Auto-generate a 1-line summary from a verification error.
        
        This is a fast heuristic — not perfect, but good enough for
        compact summaries. For better summaries, use an LLM.
        
        Extracts the most informative line from the error:
        - Last line of a traceback (the actual exception)
        - First "FAIL" or "ERROR" line
        - First line that looks like an assertion failure
        - First non-empty line as fallback
        """
        lines = error_text.strip().split("\n")
        
        # Look for common error patterns
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            # Python exception (last line of traceback)
            if any(line.startswith(prefix) for prefix in [
                "ValueError:", "TypeError:", "AttributeError:", "ImportError:",
                "AssertionError:", "KeyError:", "IndexError:", "RuntimeError:",
                "FileNotFoundError:", "NameError:", "ModuleNotFoundError:",
            ]):
                return _truncate(line, 150)
        
        # Look for FAIL/ERROR lines
        for line in lines:
            line = line.strip()
            if any(marker in line.upper() for marker in ["FAIL:", "ERROR:", "FAILED:", "MISSING"]):
                return _truncate(line, 150)
        
        # Look for assertion failures
        for line in lines:
            line = line.strip()
            if "assert" in line.lower() or "expected" in line.lower():
                return _truncate(line, 150)
        
        # Fallback: first non-empty line
        for line in lines:
            line = line.strip()
            if line:
                return _truncate(line, 150)
        
        return "Unknown verification error"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
