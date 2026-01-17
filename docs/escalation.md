# Escalation System

BOB's escalation system automatically handles task failures by progressively using more capable models and strategies.

## How It Works

When a task fails, BOB follows an escalation chain:

```
Attempt 1: Sonnet (fast, cost-effective)
    ↓ (if fails)
Attempt 2: Sonnet retry (same model, fresh attempt)
    ↓ (if fails)
Attempt 3: Opus (more capable, higher cost)
    ↓ (if fails)
Attempt 4: Diagnosis (analyze root cause)
    ↓
    ├→ Research (if knowledge gap)
    └→ Decompose (if task too complex)
```

## Escalation Strategies

### Smart (Recommended)

Balances cost and capability:

```yaml
escalation:
  strategy: smart
  max_escalations: 3
```

Flow:
1. Try Sonnet
2. Retry Sonnet (different approach)
3. Escalate to Opus
4. Diagnose → Research or Decompose

**Use when**: Most projects, good balance

### Aggressive

Escalates quickly to capable models:

```yaml
escalation:
  strategy: aggressive
  max_escalations: 2
```

Flow:
1. Try Sonnet
2. Immediately escalate to Opus
3. Diagnose → Research or Decompose

**Use when**: Time-critical, budget flexible

### Conservative

Minimizes cost, more retries:

```yaml
escalation:
  strategy: conservative
  max_escalations: 1
```

Flow:
1. Try Sonnet
2. Retry Sonnet
3. Retry Sonnet again
4. Diagnose (no Opus) → Research only

**Use when**: Budget-constrained projects

### Off

No escalation, simple retry:

```yaml
escalation:
  enabled: false
```

Flow:
1. Try Sonnet
2. Retry up to `max_retries` times
3. Mark as failed

**Use when**: Testing, known-simple tasks

## Failure Classification

Diagnosis agent classifies failures into categories:

### Knowledge Gap

Missing information or expertise.

**Example**: "Need to know the best JWT library for Python"

**Resolution**: Research
- Query Perplexity for current best practices
- Store findings
- Retry with research context

### Task Complexity

Task is too large or complex.

**Example**: "Implement entire authentication system"

**Resolution**: Decompose
- Break into subtasks
- Create new tasks with dependencies
- Execute subtasks sequentially

### Environment Issue

Problem with workspace, dependencies, or setup.

**Example**: "Module not found: 'flask'"

**Resolution**: Environment fix
- Install missing dependencies
- Fix configuration
- Retry task

### Implementation Bug

Logic error or incorrect approach.

**Example**: "Test failing due to incorrect validation logic"

**Resolution**: Retry with diagnosis insights
- Use diagnosis findings
- Apply specific fix
- Re-run tests

## Auto-Recovery

BOB can automatically recover from certain failures:

### Auto-Research

```yaml
escalation:
  auto_research: true
```

When diagnosis indicates knowledge gap:
1. Automatically run research queries
2. Store findings
3. Retry implementation with context

### Auto-Decompose

```yaml
escalation:
  auto_decompose: true
```

When diagnosis indicates complexity:
1. Automatically break down task
2. Create subtasks with dependencies
3. Queue subtasks for execution

### Manual Control

Disable auto-recovery for manual intervention:

```yaml
escalation:
  auto_research: false
  auto_decompose: false
```

BOB will:
1. Run diagnosis
2. Pause and notify user
3. Wait for manual decision

## Monitoring Escalations

### View Escalation History

```bash
# Show tasks that escalated
bob task list --escalated

# Show task escalation details
bob task show <task-id> --escalations
```

### Cost Tracking

```bash
# See escalation costs
bob costs --by-model

# Compare Sonnet vs Opus usage
bob costs --breakdown
```

Example output:
```
Model Costs:
  claude-sonnet-4: $12.50 (80% of total)
  claude-opus-4:   $ 3.00 (20% of total)

Escalation Impact: +$3.00 (24% increase)
```

## Best Practices

### 1. Start with Smart Strategy

```yaml
escalation:
  strategy: smart  # Good default
  max_escalations: 3
```

### 2. Enable Auto-Research for Complex Domains

```yaml
escalation:
  auto_research: true  # For ML, crypto, etc.
```

### 3. Monitor Escalation Rates

High escalation rate (>30%) indicates:
- Tasks are too complex
- Specs are unclear
- Research should be pre-done

### 4. Use Conservative for Budget Projects

```yaml
escalation:
  strategy: conservative
  max_escalations: 1  # Minimize Opus usage
```

### 5. Disable for Simple Projects

```yaml
escalation:
  enabled: false  # For well-defined, simple tasks
```

## Examples

### High-Quality, Time-Critical

```yaml
escalation:
  strategy: aggressive
  max_escalations: 3
  auto_research: true
  auto_decompose: true
```

### Budget-Conscious

```yaml
escalation:
  strategy: conservative
  max_escalations: 1
  auto_research: false  # Manual research
  auto_decompose: false # Manual decomposition
```

### Research-Heavy Project

```yaml
escalation:
  strategy: smart
  auto_research: true
  auto_decompose: false  # Keep tasks focused

research:
  enabled: true
  max_queries: 10  # Allow more research
```

---

See also:
- [Configuration](configuration.md) - Escalation settings
- [Research-First](research-first.md) - Research workflow
- [Architecture](architecture.md) - Escalation internals
