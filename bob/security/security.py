"""
Security Hooks for BOB Framework
=================================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.

Ported from autonomous-coding quickstart with BOB-specific enhancements:
- Configurable per-project command allowlist
- Integration with project configuration
"""

import os
import shlex
from typing import Optional, Set


# Default allowed commands for development tasks
# This is the baseline set - projects can add or restrict via config
DEFAULT_ALLOWED_COMMANDS = {
    # File inspection
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "rg",           # ripgrep - fast grep alternative
    "ag",           # silver searcher - another grep alternative
    # File operations (agent uses SDK tools for most file ops, but cp/mkdir needed occasionally)
    "cp",
    "mkdir",
    "chmod",  # For making scripts executable; validated separately
    # Directory
    "pwd",
    # Node.js development
    "npm",
    "node",
    # Python development
    "python",
    "python3",
    "pytest",
    "pip",
    "pip3",
    "uv",  # Fast Python package manager
    "source",  # For sourcing venv/bin/activate
    # Python code quality (referenced in coding_prompt.md)
    "mypy",
    "ruff",
    "black",
    "isort",
    "pyright",
    # Version control
    "git",
    # Process management
    "ps",
    "lsof",
    "sleep",
    "pkill",  # For killing dev servers; validated separately
    "kill",
    "pgrep",        # Find processes by name
    "pidof",        # Get PID of running program
    "time",         # Time command execution
    # System monitoring (useful for long-running Ray jobs)
    "top",
    "htop",
    "free",
    "df",
    "du",
    "uptime",
    "hostname",
    "id",
    "whoami",
    # Script execution
    "init.sh",  # Init scripts; validated separately
    "bash",
    "sh",
    # Container management
    "docker",
    "docker-compose",
    # EDA / Physical Design tools
    "openroad",
    "opensta",
    "yosys",
    "klayout",
    "magic",
    "netgen",
    "ngspice",
    "tcl",          # Tcl scripting for OpenROAD
    "tclsh",
    "flow.tcl",     # OpenLane flow script
    # Distributed execution (Ray)
    "ray",
    # Build tools
    "make",
    "cmake",
    # File utilities
    "touch",
    "mv",
    "rm",
    "ln",           # Symlinks
    "tar",
    "gzip",
    "gunzip",
    "unzip",
    "zip",
    "bzip2",
    "bunzip2",
    "xz",
    "unxz",
    "find",
    "xargs",
    "sort",
    "uniq",
    "diff",
    "tee",
    "tr",
    # Path utilities
    "readlink",
    "realpath",
    "dirname",
    "basename",
    "mktemp",
    "tree",
    "stat",
    "file",         # File type detection
    # Checksums (artifact verification)
    "md5sum",
    "sha256sum",
    "sha1sum",
    # Text/data processing (essential for parsing OpenROAD reports)
    "jq",       # JSON parsing - critical for telemetry/artifacts
    "awk",
    "sed",
    "cut",
    "paste",
    # Environment utilities
    "env",
    "which",
    "echo",
    "printf",
    "test",
    "true",
    "false",
    "expr",
    "date",
    # Network utilities (for downloading PDKs, etc.)
    "curl",
    "wget",
    # Network diagnostics (for Ray dashboard, port checks)
    "nc",           # netcat - check if ports are open
    "netcat",
    "ss",           # Socket statistics
    "netstat",
    # X11/GUI (for headless heatmap exports + interactive mode per app_spec.txt)
    "xvfb-run",
    "Xvfb",
    "xhost",        # Required for X11 passthrough: xhost +local:docker
    "xdpyinfo",     # Display info for debugging
    "xset",         # X settings
    "xrandr",       # Display configuration
    # Browser automation
    "npx",  # For puppeteer-mcp-server and other npm tools
    "playwright",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "firefox",
    # Background process management
    "nohup",
    "timeout",
    "wait",
    # HTTP testing
    "httpx",  # Python HTTP client CLI
    # Misc utilities
    "seq",          # Number sequences
    "yes",          # Repeated output (for automation)
    "sync",         # Flush filesystem writes
    "clear",        # Clear terminal
    "reset",        # Reset terminal
    "less",         # Pager for viewing files
    "more",         # Pager for viewing files
    "watch",        # Execute command periodically
    "column",       # Format output in columns
    "rev",          # Reverse lines
    "od",           # Octal dump (binary file inspection)
    "hexdump",      # Hex dump
    "xxd",          # Hex dump / binary editor
    # Image processing (PNG thumbnail generation for heatmaps per app_spec.txt)
    "convert",      # ImageMagick - CSV heatmap → PNG thumbnail
    "magick",       # ImageMagick 7 CLI
    "montage",      # ImageMagick - create image montages
    "identify",     # ImageMagick - identify image properties
    "gnuplot",      # Plotting tool for heatmap visualization
    # Graph visualization (case lineage graphs per app_spec.txt)
    "dot",          # Graphviz - directed graphs
    "neato",        # Graphviz - undirected graphs
    "fdp",          # Graphviz - force-directed
    "sfdp",         # Graphviz - scalable force-directed
    "circo",        # Graphviz - circular layout
    # Remote/shared filesystem (NFS/Lustre for multi-node per app_spec.txt)
    "rsync",        # Efficient file sync for artifacts
    "scp",          # Secure copy
    "ssh",          # Remote execution (validated separately if needed)
    # Container image management
    "podman",       # Docker alternative
}

# Commands that need additional validation even when in the allowlist
COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "chmod", "init.sh"}


def get_allowed_commands(project_config: Optional[dict] = None) -> Set[str]:
    """
    Get the set of allowed commands for a project.

    Projects can customize their allowlist via config:
    - security.allowed_commands: Additional commands to allow
    - security.blocked_commands: Commands to block from default set
    - security.use_defaults: Whether to include default commands (default: True)

    Args:
        project_config: Project configuration dict

    Returns:
        Set of allowed command names
    """
    if project_config is None:
        return DEFAULT_ALLOWED_COMMANDS.copy()

    security_config = project_config.get("security", {})

    # Start with defaults unless explicitly disabled
    if security_config.get("use_defaults", True):
        allowed = DEFAULT_ALLOWED_COMMANDS.copy()
    else:
        allowed = set()

    # Add project-specific allowed commands
    additional = security_config.get("allowed_commands", [])
    if additional:
        allowed.update(additional)

    # Remove blocked commands
    blocked = security_config.get("blocked_commands", [])
    if blocked:
        allowed -= set(blocked)

    return allowed


def split_command_segments(command_string: str) -> list[str]:
    """
    Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).

    Args:
        command_string: The full shell command

    Returns:
        List of individual command segments
    """
    import re

    # Split on && and || while preserving the ability to handle each segment
    # This regex splits on && or || that aren't inside quotes
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    # Further split on semicolons
    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def extract_commands(command_string: str) -> list[str]:
    """
    Extract command names from a shell command string.

    Handles pipes, command chaining (&&, ||, ;), and subshells.
    Returns the base command names (without paths).

    Args:
        command_string: The full shell command

    Returns:
        List of command names found in the string
    """
    commands = []

    # shlex doesn't treat ; as a separator, so we need to pre-process
    import re

    # Split on semicolons that aren't inside quotes (simple heuristic)
    # This handles common cases like "echo hello; ls"
    segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', command_string)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Malformed command (unclosed quotes, etc.)
            # Return empty to trigger block (fail-safe)
            return []

        if not tokens:
            continue

        # Track when we expect a command vs arguments
        expect_command = True

        for token in tokens:
            # Shell operators indicate a new command follows
            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            # Skip shell keywords that precede commands
            if token in (
                "if",
                "then",
                "else",
                "elif",
                "fi",
                "for",
                "while",
                "until",
                "do",
                "done",
                "case",
                "esac",
                "in",
                "!",
                "{",
                "}",
            ):
                continue

            # Skip flags/options
            if token.startswith("-"):
                continue

            # Skip variable assignments (VAR=value)
            if "=" in token and not token.startswith("="):
                continue

            if expect_command:
                # Extract the base command name (handle paths like /usr/bin/python)
                cmd = os.path.basename(token)
                commands.append(cmd)
                expect_command = False

    return commands


def validate_pkill_command(command_string: str) -> tuple[bool, str]:
    """
    Validate pkill commands - only allow killing dev-related processes.

    Uses shlex to parse the command, avoiding regex bypass vulnerabilities.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    # Allowed process names for pkill
    allowed_process_names = {
        "node",
        "npm",
        "npx",
        "vite",
        "next",
        # Ray distributed execution
        "ray",
        "raylet",
        "gcs_server",
        "plasma_store",
        # Browser automation
        "chromium",
        "chrome",
        "firefox",
        "playwright",
        # EDA / Physical Design tools
        "openroad",
        "opensta",
        "yosys",
        "klayout",
        "magic",
        # X11/GUI
        "Xvfb",
        "xvfb",
    }

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse pkill command"

    if not tokens:
        return False, "Empty pkill command"

    # Separate flags from arguments
    args = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return False, "pkill requires a process name"

    # The target is typically the last non-flag argument
    target = args[-1]

    # For -f flag (full command line match), extract the first word as process name
    # e.g., "pkill -f 'node server.js'" -> target is "node server.js", process is "node"
    if " " in target:
        target = target.split()[0]

    if target in allowed_process_names:
        return True, ""
    return False, f"pkill only allowed for dev processes: {allowed_process_names}"


def validate_chmod_command(command_string: str) -> tuple[bool, str]:
    """
    Validate chmod commands - only allow making files executable with +x.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse chmod command"

    if not tokens or tokens[0] != "chmod":
        return False, "Not a chmod command"

    # Look for the mode argument
    # Valid modes: +x, u+x, a+x, etc. (anything ending with +x for execute permission)
    mode = None
    files = []

    for token in tokens[1:]:
        if token.startswith("-"):
            # Skip flags like -R (we don't allow recursive chmod anyway)
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return False, "chmod requires a mode"

    if not files:
        return False, "chmod requires at least one file"

    # Only allow +x variants (making files executable)
    # This matches: +x, u+x, g+x, o+x, a+x, ug+x, etc.
    import re

    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x mode, got: {mode}"

    return True, ""


def validate_init_script(command_string: str) -> tuple[bool, str]:
    """
    Validate init.sh script execution - only allow ./init.sh.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse init script command"

    if not tokens:
        return False, "Empty command"

    # The command should be exactly ./init.sh (possibly with arguments)
    script = tokens[0]

    # Allow ./init.sh or paths ending in /init.sh
    if script == "./init.sh" or script.endswith("/init.sh"):
        return True, ""

    return False, f"Only ./init.sh is allowed, got: {script}"


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """
    Find the specific command segment that contains the given command.

    Args:
        cmd: The command name to find
        segments: List of command segments

    Returns:
        The segment containing the command, or empty string if not found
    """
    for segment in segments:
        segment_commands = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


async def bash_security_hook(input_data, tool_use_id=None, context=None, project_config=None):
    """
    Pre-tool-use hook that validates bash commands using an allowlist.

    Only commands in the allowed list are permitted. The allowed list can be
    customized per-project via project configuration.

    Args:
        input_data: Dict containing tool_name and tool_input
        tool_use_id: Optional tool use ID
        context: Optional context
        project_config: Optional project configuration dict for custom allowlist

    Returns:
        Empty dict to allow, or {"decision": "block", "reason": "..."} to block
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    # Get allowed commands for this project
    allowed_commands = get_allowed_commands(project_config)

    # Extract all commands from the command string
    commands = extract_commands(command)

    if not commands:
        # Could not parse - fail safe by blocking
        return {
            "decision": "block",
            "reason": f"Could not parse command for security validation: {command}",
        }

    # Split into segments for per-command validation
    segments = split_command_segments(command)

    # Check each command against the allowlist
    for cmd in commands:
        if cmd not in allowed_commands:
            return {
                "decision": "block",
                "reason": f"Command '{cmd}' is not in the allowed commands list",
            }

        # Additional validation for sensitive commands
        if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
            # Find the specific segment containing this command
            cmd_segment = get_command_for_validation(cmd, segments)
            if not cmd_segment:
                cmd_segment = command  # Fallback to full command

            if cmd == "pkill":
                allowed, reason = validate_pkill_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "chmod":
                allowed, reason = validate_chmod_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "init.sh":
                allowed, reason = validate_init_script(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}

    return {}
