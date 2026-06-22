# MPI Collective Communication Idioms

## Initialization and Teardown

```c
MPI_Init(&argc, &argv);
int rank, size;
MPI_Comm_rank(MPI_COMM_WORLD, &rank);
MPI_Comm_size(MPI_COMM_WORLD, &size);
// ... work ...
MPI_Finalize();
```

## Point-to-Point Communication

```c
// Blocking send / receive
MPI_Send(buf, count, MPI_DOUBLE, dest, tag, MPI_COMM_WORLD);
MPI_Recv(buf, count, MPI_DOUBLE, src,  tag, MPI_COMM_WORLD, MPI_STATUS_IGNORE);

// Non-blocking — overlap compute with communication
MPI_Request req;
MPI_Isend(buf, count, MPI_DOUBLE, dest, tag, MPI_COMM_WORLD, &req);
// ... do other work ...
MPI_Wait(&req, MPI_STATUS_IGNORE);
```

## Collective Operations

### Broadcast
```c
// Root sends the same data to all ranks
MPI_Bcast(buf, count, MPI_DOUBLE, root, MPI_COMM_WORLD);
```

### Scatter / Gather
```c
// Root splits sendbuf into equal chunks, one per rank
MPI_Scatter(sendbuf, count, MPI_DOUBLE,
            recvbuf, count, MPI_DOUBLE,
            root, MPI_COMM_WORLD);

// Inverse: each rank contributes a chunk → root assembles
MPI_Gather(sendbuf, count, MPI_DOUBLE,
           recvbuf, count, MPI_DOUBLE,
           root, MPI_COMM_WORLD);

// All-to-all gather: every rank gets the full assembled array
MPI_Allgather(sendbuf, count, MPI_DOUBLE,
              recvbuf, count, MPI_DOUBLE,
              MPI_COMM_WORLD);
```

### Reduction
```c
// Reduce to root
MPI_Reduce(sendbuf, recvbuf, count, MPI_DOUBLE,
           MPI_SUM, root, MPI_COMM_WORLD);

// Reduce to all ranks
MPI_Allreduce(sendbuf, recvbuf, count, MPI_DOUBLE,
              MPI_SUM, MPI_COMM_WORLD);
```

### Barrier
```c
MPI_Barrier(MPI_COMM_WORLD);  // synchronize all ranks
```

## Common MPI Datatypes

| C type | MPI type |
|--------|---------|
| `int` | `MPI_INT` |
| `double` | `MPI_DOUBLE` |
| `float` | `MPI_FLOAT` |
| `long` | `MPI_LONG` |
| `char` | `MPI_CHAR` |

Custom struct types: use `MPI_Type_create_struct` + `MPI_Type_commit`.

## Domain Decomposition Pattern

```c
int local_n = N / size;
int remainder = N % size;
// Give remainder to last rank
if (rank == size - 1) local_n += remainder;

double *local_data = malloc(local_n * sizeof(double));
MPI_Scatter(global_data, N / size, MPI_DOUBLE,
            local_data,  N / size, MPI_DOUBLE,
            0, MPI_COMM_WORLD);
// process local_data ...
MPI_Gather(local_data,  N / size, MPI_DOUBLE,
           global_data, N / size, MPI_DOUBLE,
           0, MPI_COMM_WORLD);
```

## Halo Exchange (Stencil Pattern)

```c
// Send right boundary to right neighbor, receive from left neighbor
MPI_Sendrecv(
    right_boundary, halo_size, MPI_DOUBLE, rank + 1, 0,
    left_halo,      halo_size, MPI_DOUBLE, rank - 1, 0,
    MPI_COMM_WORLD, MPI_STATUS_IGNORE);
```

## Persistent Requests (Reduce Setup Overhead)

```c
MPI_Request req;
MPI_Send_init(buf, count, MPI_DOUBLE, dest, tag, MPI_COMM_WORLD, &req);
// Reuse in a loop:
MPI_Start(&req);
// ... compute ...
MPI_Wait(&req, MPI_STATUS_IGNORE);
MPI_Request_free(&req);
```

## Common Pitfalls

- **Deadlock**: symmetric blocking sends without matching receives → use `MPI_Sendrecv` or non-blocking.
- **Buffer aliasing**: `sendbuf == recvbuf` is undefined in most collectives; use `MPI_IN_PLACE` explicitly.
- **Tag mismatch**: messages received out of order → use `MPI_ANY_TAG` carefully or structure tag space.
- **Large message latency**: for messages > eager threshold, use non-blocking + overlap.
