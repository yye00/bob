"""
Debug Journal — MemGPT-style Retrieval for Debug Context
=========================================================

Instead of stuffing the full debug history into every prompt (which eats
the context window and puts Claude in the "dumb zone"), we:

1. Store full debug history on disk at .bob/debug/<task_id>.md
2. Inject only a compact summary into the debug prompt (~200 tokens)
3. Tell Claude where the journal is so it can read it on-demand via tools

This keeps the working context lean while giving Claude full access to
debug history through its file-read tools.
"""

import json
import os
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
        """Record that debugging succeeded."""
        path = self.journal_path(spec_id)
        if not path.exists():
            return
        
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
        """Remove a task's debug journal (e.g., on task reset)."""
        path = self.journal_path(spec_id)
        if path.exists():
            path.unlink()
    
    def list_journals(self) -> list[dict]:
        """List all debug journals with basic info."""
        journals = []
        for path in sorted(self.debug_dir.glob("*.md")):
            content = path.read_text()
            attempt_count = content.count("## Debug Attempt")
            resolved = "RESOLVED" in content
            spec_id = path.stem
            journals.append({
                "spec_id": spec_id,
                "attempts": attempt_count,
                "resolved": resolved,
                "path": str(path),
            })
        return journals
    
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
