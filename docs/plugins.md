# Plugin Development Guide

BOB's plugin system allows you to extend functionality with custom agents, spec sources, and tools.

## Plugin Types

### 1. Spec Source Plugins

Add custom spec sources (Jira, Linear, Notion, etc.):

```python
from bob.plugins.base import SpecSourcePlugin

class JiraSpecSource(SpecSourcePlugin):
    """Fetch tasks from Jira."""

    def fetch_tasks(self, source_uri: str) -> list[dict]:
        """Fetch tasks from Jira API."""
        # Parse URI: jira://project-key/filter-id
        project, filter_id = self.parse_uri(source_uri)

        # Fetch from Jira API
        issues = self.jira_client.get_issues(filter_id)

        # Convert to BOB task format
        return [self.convert_issue(issue) for issue in issues]

    def convert_issue(self, issue: dict) -> dict:
        """Convert Jira issue to BOB task."""
        return {
            "id": issue["key"],
            "title": issue["summary"],
            "description": issue["description"],
            "priority": self.map_priority(issue["priority"]),
            "depends_on": self.extract_dependencies(issue),
        }
```

Register plugin:
```python
# ~/.bob/plugins/jira_plugin.py
from bob.plugins.registry import register_plugin

register_plugin("jira", JiraSpecSource)
```

### 2. Agent Plugins

Add custom agent types:

```python
from bob.plugins.base import AgentPlugin

class SecurityAuditAgent(AgentPlugin):
    """Agent that performs security audits."""

    def execute(self, task: dict, context: dict) -> dict:
        """Run security audit on code."""
        # Run security scanning tools
        results = self.scan_code(task["workspace"])

        # Analyze vulnerabilities
        vulns = self.analyze_results(results)

        # Generate report
        return {
            "status": "completed" if len(vulns) == 0 else "failed",
            "vulnerabilities": vulns,
            "report": self.generate_report(vulns)
        }
```

### 3. Tool Plugins

Add custom tools for agents:

```python
from bob.plugins.base import ToolPlugin

class DatabaseMigrationTool(ToolPlugin):
    """Tool for database migrations."""

    def run_migration(self, migration_file: str) -> dict:
        """Run database migration."""
        # Execute migration
        result = self.db.execute_migration(migration_file)

        return {
            "success": result.success,
            "version": result.version,
            "output": result.output
        }
```

## Plugin Structure

```
~/.bob/plugins/
├── my_plugin/
│   ├── __init__.py
│   ├── plugin.py       # Main plugin code
│   ├── config.yaml     # Plugin configuration
│   └── README.md       # Documentation
```

## Plugin Configuration

```yaml
# ~/.bob/plugins/my_plugin/config.yaml
name: my-plugin
version: 1.0.0
description: Custom plugin for BOB
author: Your Name

type: spec_source  # or agent, tool

settings:
  api_key: ${MY_PLUGIN_API_KEY}
  base_url: https://api.example.com
```

## Using Plugins

```bash
# List installed plugins
bob plugin list

# Install plugin
bob plugin install ./my-plugin

# Enable plugin
bob plugin enable my-plugin

# Configure plugin
bob plugin config my-plugin set api_key your_key

# Use plugin
bob project create my-proj ./workspace my-plugin://source-uri
```

## Best Practices

1. **Validate inputs** - Check all parameters
2. **Handle errors** - Graceful failure with clear messages
3. **Cache results** - Avoid redundant API calls
4. **Document usage** - Clear README and examples
5. **Test thoroughly** - Unit and integration tests

---

For complete plugin API reference, see the [Architecture](architecture.md) document.
