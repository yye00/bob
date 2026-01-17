# Microservices Platform - BOB Example

This example demonstrates **parallel task execution** where independent tasks can run simultaneously, significantly reducing overall project completion time.

## What This Example Shows

- **Parallel execution**: Multiple tasks with no dependencies run concurrently
- **Dependency management**: Tasks wait for dependencies before starting
- **Resource optimization**: Maximum CPU/API utilization
- **Clear parallelization groups**: Tasks labeled by parallel group

## Project Overview

Build a complete microservices platform with:
- **3 Core Services**: User, Product, Order (can build in parallel)
- **3 Infrastructure Services**: API Gateway, Notifications, Analytics (can build in parallel)
- **Monitoring Stack**: Prometheus, Grafana, Jaeger
- **Kubernetes Deployment**: Helm charts and manifests

## Parallelization Strategy

### Wave 1: Foundation (Sequential)
```
shared-lib (MUST complete first)
```

### Wave 2: Services (PARALLEL - 6 tasks)
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  user-service   │  │ product-service │  │  order-service  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  api-gateway    │  │  notification   │  │   analytics     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
┌─────────────────┐  ┌─────────────────┐
│   monitoring    │  │  documentation  │
└─────────────────┘  └─────────────────┘

ALL depend on: shared-lib
ALL run in PARALLEL (9 tasks at once!)
```

### Wave 3: Integration (Sequential)
```
integration-tests (waits for: user, product, order, gateway)
```

### Wave 4: Dockerization (PARALLEL - 4 tasks)
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  user-docker │  │product-docker│  │ order-docker │  │gateway-docker│
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### Wave 5: Orchestration (Sequential)
```
kubernetes-deploy (waits for all Docker images)
```

## Time Savings with Parallel Execution

### Sequential Execution Time
```
shared-lib:          30 min
user-service:        45 min
product-service:     45 min
order-service:       45 min
api-gateway:         30 min
notification:        30 min
analytics:           30 min
monitoring:          30 min
documentation:       20 min
integration-tests:   20 min
dockerization (4x):  40 min
kubernetes:          20 min
──────────────────────────
TOTAL:              385 min (6.4 hours)
```

### Parallel Execution Time
```
Wave 1 (sequential):  30 min (shared-lib)
Wave 2 (parallel):    45 min (slowest of 9 parallel tasks)
Wave 3 (sequential):  20 min (integration-tests)
Wave 4 (parallel):    10 min (dockerization)
Wave 5 (sequential):  20 min (kubernetes)
──────────────────────────
TOTAL:               125 min (2.1 hours)

TIME SAVED: 260 min (67% faster!)
```

## Running This Example with BOB

```bash
# Create the project
bob project create microservices \
  --spec examples/parallel-tasks/spec.yaml \
  --workspace ./workspace/microservices

# Run with parallel execution enabled (default)
bob run --project microservices

# Run with maximum parallelism
bob run --project microservices --max-parallel 10

# Monitor parallel execution
bob status --project microservices
```

## Expected BOB Behavior

1. **Start**: Runs `shared-lib` (only task with no dependencies)

2. **Parallel Wave**: Once `shared-lib` completes, BOB starts 9 tasks simultaneously:
   - user-service
   - product-service
   - order-service
   - api-gateway-service
   - notification-service
   - analytics-service
   - monitoring-stack
   - api-documentation

3. **Dependency Wait**: `integration-tests` waits for 4 specific services

4. **Docker Wave**: Once services complete, Dockerization runs in parallel

5. **Final Deploy**: Kubernetes deployment runs after all Docker images ready

## Parallel Execution Labels

Tasks are labeled to show parallel grouping:

- `parallel-group-a`: Core services (user, product, order)
- `parallel-group-b`: Infrastructure (gateway, notification, analytics, monitoring, docs)
- `parallel-group-c`: Dockerization (4 Docker images)

## Expected Outcome

After BOB completes all tasks, you'll have:
- **3 Microservices**: User, Product, Order
- **API Gateway**: Routes and authentication
- **Supporting Services**: Notifications and Analytics
- **Monitoring**: Prometheus, Grafana, Jaeger
- **Docker Images**: All services containerized
- **Kubernetes**: Deployment manifests and Helm chart
- **Documentation**: Complete API docs

## Console Output Example

```
[12:00:00] Starting: shared-lib
[12:30:00] ✓ Completed: shared-lib

[12:30:01] Starting: user-service (parallel 1/9)
[12:30:01] Starting: product-service (parallel 2/9)
[12:30:01] Starting: order-service (parallel 3/9)
[12:30:01] Starting: api-gateway-service (parallel 4/9)
[12:30:01] Starting: notification-service (parallel 5/9)
[12:30:01] Starting: analytics-service (parallel 6/9)
[12:30:01] Starting: monitoring-stack (parallel 7/9)
[12:30:01] Starting: api-documentation (parallel 8/9)

[13:00:00] ✓ Completed: notification-service (1/9)
[13:05:00] ✓ Completed: monitoring-stack (2/9)
[13:10:00] ✓ Completed: api-documentation (3/9)
[13:15:00] ✓ Completed: user-service (4/9)
[13:15:00] ✓ Completed: product-service (5/9)
[13:15:00] ✓ Completed: order-service (6/9)
[13:15:00] ✓ Completed: api-gateway-service (7/9)
[13:15:00] ✓ Completed: analytics-service (8/9)

[13:15:01] Starting: integration-tests
[13:35:00] ✓ Completed: integration-tests

[13:35:01] Starting: user-service-docker (parallel 1/4)
[13:35:01] Starting: product-service-docker (parallel 2/4)
[13:35:01] Starting: order-service-docker (parallel 3/4)
[13:35:01] Starting: gateway-docker (parallel 4/4)

[13:45:00] ✓ All Docker images completed

[13:45:01] Starting: kubernetes-deploy
[14:05:00] ✓ Completed: kubernetes-deploy

✓ All tasks completed in 2.1 hours
```

## Learning from This Example

This spec teaches:
- **Identifying parallel opportunities**: Tasks with independent dependencies
- **Dependency design**: Minimal dependencies enable maximum parallelism
- **Resource utilization**: Keep CI/CD pipelines busy with parallel tasks
- **Project structure**: Organize for parallel development (separate services)
- **Time optimization**: 67% faster completion through parallelization
