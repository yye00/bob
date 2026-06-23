# OpenMP Pragma Patterns

## Core Threading Directives

```c
// Parallel region — all threads execute the block
#pragma omp parallel
{
    int tid = omp_get_thread_num();
}

// Fork-join with shared work
#pragma omp parallel for schedule(static)
for (int i = 0; i < N; i++) {
    a[i] = b[i] + c[i];
}

// Reduction across threads
#pragma omp parallel for reduction(+:sum)
for (int i = 0; i < N; i++) {
    sum += a[i];
}
```

## Data Scoping Clauses

| Clause | Meaning |
|--------|---------|
| `shared(x)` | All threads read/write the same `x` |
| `private(x)` | Each thread gets its own uninitialized copy |
| `firstprivate(x)` | Private copy initialized from master thread's value |
| `lastprivate(x)` | Master gets the value from the last iteration |
| `reduction(op:x)` | Thread-local copies combined with `op` at join |

## Scheduling Strategies

```c
// Static: equal chunks, round-robin (predictable, cache-friendly for uniform work)
#pragma omp parallel for schedule(static)

// Dynamic: chunks grabbed on demand (good for irregular work)
#pragma omp parallel for schedule(dynamic, 64)

// Guided: decreasing chunk sizes (balances overhead vs. load)
#pragma omp parallel for schedule(guided)
```

## Synchronization

```c
// Critical section — only one thread at a time
#pragma omp critical
{ shared_counter++; }

// Atomic — cheaper than critical for simple operations
#pragma omp atomic
shared_counter++;

// Barrier — all threads wait here before proceeding
#pragma omp barrier

// Single — only one thread executes the block
#pragma omp single
{ init_once(); }
```

## SIMD Integration

```c
// Vectorize the loop AND parallelize across threads
#pragma omp parallel for simd
for (int i = 0; i < N; i++) {
    c[i] = a[i] * b[i];
}
```

## Task-Based Parallelism (OpenMP 3.0+)

```c
#pragma omp parallel
#pragma omp single
{
    for (int i = 0; i < N; i++) {
        #pragma omp task
        process(data[i]);
    }
}  // implicit taskwait at end of single
```

## Common Pitfalls

- **False sharing**: threads updating adjacent cache lines → pad structs or use `private`.
- **Race conditions**: writing `shared` variables inside `parallel for` without `atomic`/`critical`.
- **Stack overflow**: `private` arrays larger than stack limit → allocate on heap inside region.
- **Nested parallelism**: disabled by default; enable with `omp_set_nested(1)` or `OMP_NESTED=true`.

## Environment Variables

```bash
OMP_NUM_THREADS=8          # override thread count
OMP_SCHEDULE="dynamic,64"  # override default schedule
OMP_PROC_BIND=close        # bind threads to nearby cores
```
