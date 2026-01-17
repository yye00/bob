# Research-First Workflow

The research-first workflow prevents wasted attempts on tasks that require external knowledge or expertise.

## Concept

Instead of having the AI agent attempt implementation and fail repeatedly, BOB can:

1. **Identify** tasks requiring research (marked in spec or auto-detected)
2. **Research** the topic using Perplexity or web search
3. **Store** findings for future reference
4. **Implement** using research context

## Marking Tasks for Research

### In Spec File

```yaml
tasks:
  - id: jwt-auth
    title: Implement JWT Authentication
    description: Secure JWT-based auth system
    research_required: true
    research_queries:
      - "JWT token storage best practices 2026"
      - "Secure HTTP-only cookie vs localStorage"
      - "JWT refresh token rotation strategies"
```

### Auto-Detection

BOB can auto-detect when research is needed:

```yaml
tasks:
  - id: implement-ml-model
    description: |
      Implement a transformer model for text classification.
      Not sure which framework is best.
```

Keywords that trigger auto-research:
- "not sure", "need to research", "which is best"
- "compare", "evaluate", "best practices"
- "latest", "current", "modern approaches"

## Research Workflow

### Automatic (Recommended)

```yaml
escalation:
  auto_research: true

research:
  enabled: true
  provider: perplexity
  max_queries: 5
```

Flow:
1. Task marked `research_required: true`
2. BOB automatically runs research queries
3. Findings stored in task metadata
4. Implementation proceeds with research context

### Manual

```yaml
escalation:
  auto_research: false
```

Flow:
1. Task marked for research
2. BOB pauses and notifies user
3. User runs: `bob research --task-id jwt-auth`
4. User reviews findings
5. User runs: `bob run --task-id jwt-auth`

## Research Commands

### Run Research

```bash
# Research specific task
bob research --task-id jwt-auth

# Research with custom queries
bob research --task-id jwt-auth \
  --query "JWT security 2026" \
  --query "Token refresh patterns"

# Research all tasks needing it
bob research --all
```

### View Research Findings

```bash
# Show research for task
bob research --show --task-id jwt-auth

# Export as JSON
bob research --show --task-id jwt-auth --json
```

### List Tasks Needing Research

```bash
# Show tasks marked for research
bob task list --needs-research

# Show tasks with research complete
bob task list --research-complete
```

## Research Providers

### Perplexity (Recommended)

Most accurate, cites sources:

```yaml
research:
  provider: perplexity
  perplexity:
    model: sonar-pro  # or sonar, sonar-reasoning
    max_tokens: 4000
```

Cost: ~$0.001 per query

### Web Search

Built-in, free option:

```yaml
research:
  provider: web_search
  web_search:
    engine: google  # or bing, duckduckgo
    max_results: 10
```

Cost: Free

## Research Cache

BOB caches research results to avoid duplicate queries:

```yaml
research:
  cache_results: true
  cache_ttl: 86400  # 24 hours
```

Benefits:
- Saves API costs
- Faster subsequent runs
- Consistent results

Clear cache:
```bash
bob research --clear-cache
bob research --clear-cache --task-id jwt-auth
```

## Writing Good Research Queries

### Good Queries

Specific, with year for current information:

```yaml
research_queries:
  - "JWT vs session cookies security comparison 2026"
  - "argon2 vs bcrypt password hashing performance 2026"
  - "React 19 server components best practices"
```

### Bad Queries

Too vague or outdated:

```yaml
research_queries:
  - "authentication"  # Too vague
  - "best JWT library"  # Which language? Year?
  - "how to hash passwords"  # Missing specifics
```

## Research in Implementation

Research findings are automatically included in agent context:

```python
# Agent receives:
"""
RESEARCH FINDINGS for task: jwt-auth

Query: "JWT token storage best practices 2026"
Source: Perplexity Sonar Pro

Key Points:
1. Use HTTP-only cookies for token storage (not localStorage)
2. Implement refresh token rotation
3. Set appropriate token expiration (15min access, 7day refresh)
4. Use secure, sameSite strict cookie flags
5. Implement CSRF protection

Based on: [OWASP JWT Cheat Sheet], [Auth0 Best Practices]

---

Proceed with implementation using these findings.
"""
```

## Examples

### Research-Heavy Project

```yaml
name: AI Model Deployment
description: Deploy ML models with current best practices

tasks:
  - id: choose-framework
    title: Select ML Framework
    research_required: true
    research_queries:
      - "PyTorch vs TensorFlow 2026 production deployment"
      - "ONNX runtime performance comparison"
      - "ML model serving frameworks comparison Triton vs TorchServe"
    steps:
      - Research current frameworks
      - Compare performance and ecosystem
      - Choose based on requirements
      - Document decision

  - id: model-optimization
    title: Optimize Model for Production
    depends_on: [choose-framework]
    research_required: true
    research_queries:
      - "Model quantization techniques 2026"
      - "TensorRT optimization best practices"
      - "ONNX model conversion gotchas"
```

### Selective Research

```yaml
tasks:
  # No research needed - straightforward
  - id: setup-project
    title: Project Setup
    research_required: false

  # Research needed - complex decision
  - id: choose-database
    title: Select Database
    research_required: true
    research_queries:
      - "PostgreSQL vs MongoDB for multi-tenant SaaS 2026"
      - "Database partitioning strategies large scale"

  # No research - implementation follows research
  - id: implement-database
    title: Implement Database Layer
    depends_on: [choose-database]
    research_required: false
```

## Best Practices

### 1. Mark Uncertain Tasks

If you're not sure of the best approach, require research:

```yaml
- id: caching-strategy
  description: Not sure if Redis or Memcached is better
  research_required: true
  research_queries:
    - "Redis vs Memcached 2026 performance"
```

### 2. Pre-Research Complex Domains

For ML, crypto, security - always research first:

```yaml
defaults:
  research_required: true  # All tasks need research

tasks:
  - id: ml-model
  - id: encryption
  - id: auth-system
```

### 3. Use Specific Queries

Include year, framework, use case:

```yaml
research_queries:
  - "React 19 state management Zustand vs Redux 2026"
  # Not: "state management"
```

### 4. Review Findings Before Implementation

Manual review for critical decisions:

```bash
# Research
bob research --task-id auth-system

# Review findings
bob research --show --task-id auth-system

# Then implement
bob run --task-id auth-system
```

### 5. Cache Results

Enable caching for consistent results:

```yaml
research:
  cache_results: true
  cache_ttl: 86400  # 24 hours
```

---

See also:
- [Configuration](configuration.md) - Research settings
- [Spec Formats](spec-formats.md) - Marking tasks for research
- [Escalation](escalation.md) - Auto-research on failure
