# Modern API Gateway - BOB Example

This example demonstrates a **research-heavy project** where tasks require online research before implementation. BOB will use Perplexity integration to research best practices and make informed architectural decisions.

## What This Example Shows

- **Research tasks**: Tasks marked with `research_required: true`
- **Research queries**: Suggested searches for the AI agent
- **Informed decisions**: Implementation based on research findings
- **Complex architecture**: API gateway with multiple advanced features
- **Decision documentation**: Research findings inform implementation

## Project Overview

Build a production-ready API gateway with:
- **Reverse Proxy**: Routes requests to backend services
- **Rate Limiting**: Distributed rate limiting with Redis
- **Response Caching**: Intelligent caching with Redis
- **Load Balancing**: Multiple algorithms (round-robin, least-connections)
- **Authentication**: API keys and JWT tokens
- **Metrics**: Prometheus metrics and Grafana dashboards

## Research-First Workflow

This project demonstrates BOB's research capabilities:

1. **Research Phase** (Tasks with `research_required: true`):
   - Agent uses Perplexity to research API gateway patterns
   - Compares different algorithms (rate limiting, caching)
   - Documents findings before implementation

2. **Decision Phase**:
   - Agent creates decision documents based on research
   - Selects appropriate patterns and algorithms
   - Justifies choices with research evidence

3. **Implementation Phase**:
   - Implementation tasks depend on research tasks
   - Code follows patterns discovered through research
   - Architecture aligns with best practices

## Task Categories

### Research Tasks (Priority 1)
- `research-api-gateway-patterns`: Compare Kong, Traefik, NGINX
- `research-rate-limiting`: Token bucket vs Leaky bucket vs Sliding window
- `research-caching-strategies`: Write-through vs Write-back vs Cache-aside

### Implementation Tasks
- `proxy-core`: Basic reverse proxy
- `rate-limiter`: Implements researched algorithm
- `caching-layer`: Implements researched caching strategy
- `load-balancer`: Round-robin and least-connections
- `auth-middleware`: API key and JWT authentication
- `metrics`: Prometheus and Grafana

## Running This Example with BOB

```bash
# Create the project
bob project create api-gateway \
  --spec examples/research-heavy/spec.yaml \
  --workspace ./workspace/api-gateway

# Run the agent (will automatically research before implementing)
bob run --project api-gateway

# Monitor progress
bob status --project api-gateway
bob logs --follow
```

## Expected Outcome

After BOB completes all tasks, you'll have:
- **Research documentation** in `docs/research/` explaining architectural decisions
- **Working API gateway** with all features implemented
- **Configuration** for rate limiting, caching, load balancing
- **Metrics** exposed for Prometheus
- **Tests** including load testing
- **Docker** and Kubernetes deployment files
- **Documentation** linking implementation to research findings

## Research Integration

BOB will execute research tasks like this:

```python
# For task: research-rate-limiting
1. Use Perplexity to search: "rate limiting algorithms comparison 2024"
2. Use Perplexity to search: "token bucket vs leaky bucket vs sliding window"
3. Use Perplexity to search: "distributed rate limiting with Redis patterns"
4. Synthesize findings into decision document
5. Mark research_complete: true
6. Proceed to implementation task (rate-limiter)
```

## Learning from This Example

This spec teaches:
- **When to research**: Complex architectural decisions benefit from research
- **How to structure research**: Clear research_queries guide the agent
- **Research → Implementation**: Dependencies ensure research completes first
- **Documentation**: Research findings are documented for future reference
- **Best practices**: Implementation follows industry best practices discovered through research

## Example Research Output

After research tasks, you'll find documents like:

### `docs/research/api-gateway-patterns.md`
```markdown
# API Gateway Architecture Research

## Comparison of Solutions
- **Kong**: Plugin-based, Lua scripting, commercial support
- **Traefik**: Cloud-native, automatic service discovery
- **NGINX**: Mature, high performance, complex configuration

## Decision: Traefik
Selected for automatic service discovery and cloud-native design.
Reasoning: Best fit for Kubernetes deployment...
```

### `docs/research/rate-limiting-algorithm.md`
```markdown
# Rate Limiting Algorithm Research

## Algorithms Compared
1. Token Bucket: Allows bursts, smooth rate limiting
2. Leaky Bucket: Constant rate, no bursts
3. Sliding Window: Precise, higher memory cost

## Decision: Token Bucket
Selected for balance of burst handling and simplicity.
Implementation: Redis-backed distributed token bucket...
```
