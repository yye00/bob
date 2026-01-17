# Session 34 Summary - Custom Prompts Per Project

**Date:** 2026-01-16
**Feature Completed:** F047 - Custom prompts per project

## Overview

Implemented project-specific prompt override functionality, allowing each project to customize agent prompts while falling back to global defaults.

## Implementation

### New Files

1. **bob/prompts/loader.py** (169 lines)
   - `PromptLoader` class for loading prompts with priority-based fallback
   - Searches project `.bob/prompts/` directory first, then global `bob/prompts/`
   - Methods:
     - `load_prompt()` - Load and render a prompt with context
     - `get_prompt_source()` - Determine if prompt is project or global
     - `list_available_prompts()` - List all prompts with their sources
   - Factory function: `create_prompt_loader()`

2. **tests/test_prompt_loader.py** (337 lines, 22 tests)
   - Comprehensive test coverage for PromptLoader
   - Tests initialization, loading, fallback, source detection, listing

### Modified Files

1. **bob/cli/project.py**
   - Added prompts directory creation in `create_workspace_structure()`
   - Added prompts section to project.yaml config
   - Updated documentation

2. **tests/test_cli_project.py**
   - Added `test_creates_prompts_directory`
   - Updated `test_project_yaml_structure` to validate prompts section

3. **feature_list.json**
   - Marked F047 as passing with timestamp

## Features

- **Priority-based Loading**: Project prompts override global prompts
- **Automatic Fallback**: Missing project prompts use global defaults
- **Easy Integration**: Simple factory function for creating loaders
- **Introspection**: Methods to check prompt sources and list available prompts
- **Template Support**: Works with existing Jinja2 TemplateEngine

## Project Structure

```
workspace/
├── .bob/
│   ├── project.yaml       # Config with prompts section
│   ├── prompts/           # Custom prompt overrides (NEW)
│   │   ├── coding_prompt.md      # Optional override
│   │   └── research_prompt.md    # Optional override
│   ├── logs/
│   └── state/
└── [project files...]
```

## Usage Example

```python
from bob.prompts.loader import create_prompt_loader
from pathlib import Path

# Create loader for a project
loader = create_prompt_loader(
    project_workspace_dir=Path("/path/to/workspace")
)

# Load coding prompt (checks project first, then global)
context = {
    "project": {
        "name": "my-app",
        "tech_stack": "Python"
    },
    "task": {
        "title": "Implement feature X"
    }
}
prompt = loader.load_prompt("coding_prompt.md", context)

# Check where prompt came from
source = loader.get_prompt_source("coding_prompt.md")
# Returns: 'project' or 'global'

# List all available prompts
prompts = loader.list_available_prompts()
# Returns: {'coding_prompt.md': 'project', 'research_prompt.md': 'global', ...}
```

## Test Results

- **Total Tests:** 955 (+23 new)
- **All Passing:** ✅
- **Coverage:** 100% for PromptLoader
- **No Regressions:** ✅

## Progress

- **Features Passing:** 57/75 (76%)
- **Features Remaining:** 18
- **Tests Added:** 23
- **Lines Added:** ~500

## Next Priorities

Ready features with dependencies satisfied:
- F055: Spec sync integration test
- F056: Checkpoint resume integration test
- F058: Dependency graph validation
- F060: Structured logging test
- F064: Unit tests for TaskQueue
- F065: Unit tests for CostTracker
- F066: Unit tests for ResearchController
- F069: CLI output formatting
- F071: Documentation

## Commits

1. `1cbf936` - Implement F047: Custom prompts per project - all tests passing
2. `3de4293` - Update progress notes - Session 34 complete: F047 implemented

## Status

✅ Session complete - Clean working tree - All tests passing
