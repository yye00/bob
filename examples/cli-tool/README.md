# File Analyzer CLI - BOB Example

This example demonstrates building a command-line tool with BOB, showcasing proper CLI design patterns, argument parsing, and file operations.

## What This Example Shows

- **CLI framework**: Using Click for command-line interfaces
- **File operations**: Safe file reading with encoding detection
- **Data processing**: Text analysis and statistics calculation
- **Multiple commands**: Main command group with subcommands
- **Output formatting**: Rich console output and multiple export formats
- **Configuration**: YAML-based configuration file support
- **Testing**: Unit tests with pytest

## Project Overview

File Analyzer is a CLI tool that analyzes text files and provides statistics such as:
- Line count, word count, character count
- Most common words
- Average word length
- Side-by-side file comparisons
- Export to JSON, CSV, or Markdown

## Task Dependency Graph

```
project-init
    ├── cli-framework
    │       ├── analyze-command
    │       │       ├── compare-command
    │       │       └── export-feature
    │       └── config-file
    └── file-reader
            └── stats-calculator
                    ├── analyze-command (already listed)
                    └── unit-tests

documentation (depends on: analyze-command, compare-command, export-feature)
package-distribution (depends on: project-init, documentation)
```

## Running This Example with BOB

```bash
# Create the project
bob project create file-analyzer \
  --spec examples/cli-tool/spec.yaml \
  --workspace ./workspace/file-analyzer

# Run the agent
bob run --project file-analyzer

# Monitor progress
bob status --project file-analyzer
```

## Expected Outcome

After BOB completes all tasks, you'll have:
- A working Python CLI tool installable via pip
- Main `analyze` command for file analysis
- `compare` command for comparing multiple files
- Export functionality (JSON, CSV, Markdown)
- Configuration file support
- Comprehensive test suite (80%+ coverage)
- Full documentation
- Ready for PyPI distribution

## Example Usage (after building)

```bash
# Install the tool
pip install -e .

# Analyze a file
file-analyzer analyze myfile.txt

# Analyze multiple files with glob
file-analyzer analyze *.log

# Compare files
file-analyzer compare file1.txt file2.txt file3.txt

# Export analysis to JSON
file-analyzer analyze data.txt --output report.json --format json

# Use custom config
file-analyzer --config my-config.yaml analyze file.txt
```

## Learning from This Example

This spec teaches:
- **CLI design patterns**: Command groups, arguments, options
- **Error handling**: Graceful handling of file errors and edge cases
- **Testing strategy**: Unit tests for core logic
- **Configuration**: Layered configuration (defaults → config file → CLI flags)
- **Output formatting**: Multiple output formats for different use cases
- **Packaging**: Proper Python package structure for distribution
