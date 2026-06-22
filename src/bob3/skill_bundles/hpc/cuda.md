# CUDA Launch Configuration and Shared-Memory Tiling

## Kernel Anatomy

```cuda
// __global__ runs on GPU, called from CPU
__global__ void vector_add(const float* a, const float* b, float* c, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) c[idx] = a[idx] + b[idx];
}
```

## Launch Configuration

```cuda
int n = 1 << 20;  // 1M elements
int block_size = 256;  // threads per block (must be multiple of 32; 128–512 typical)
int grid_size  = (n + block_size - 1) / block_size;  // ceil(n / block_size)

vector_add<<<grid_size, block_size>>>(d_a, d_b, d_c, n);
cudaDeviceSynchronize();  // wait for kernel to finish; also surfaces errors
```

### 2-D / 3-D Grids

```cuda
dim3 block(16, 16);                   // 256 threads/block
dim3 grid((W + 15) / 16, (H + 15) / 16);
matrix_kernel<<<grid, block>>>(d_mat, W, H);
```

## Shared Memory Tiling

Shared memory is ~100× faster than global memory but is only ~48–164 KB per SM.

```cuda
#define TILE 32

__global__ void matmul(const float* A, const float* B, float* C, int N) {
    __shared__ float tA[TILE][TILE];
    __shared__ float tB[TILE][TILE];

    int row = blockIdx.y * TILE + threadIdx.y;
    int col = blockIdx.x * TILE + threadIdx.x;
    float acc = 0.f;

    for (int t = 0; t < (N + TILE - 1) / TILE; t++) {
        // Load tile into shared memory
        tA[threadIdx.y][threadIdx.x] = (row < N && t * TILE + threadIdx.x < N)
            ? A[row * N + t * TILE + threadIdx.x] : 0.f;
        tB[threadIdx.y][threadIdx.x] = (col < N && t * TILE + threadIdx.y < N)
            ? B[(t * TILE + threadIdx.y) * N + col] : 0.f;

        __syncthreads();   // ensure all threads finished loading

        for (int k = 0; k < TILE; k++) acc += tA[threadIdx.y][k] * tB[k][threadIdx.x];

        __syncthreads();   // ensure compute finished before next load
    }

    if (row < N && col < N) C[row * N + col] = acc;
}
```

## Memory Management

```cuda
float *d_a;
cudaMalloc(&d_a, n * sizeof(float));                    // device allocation
cudaMemcpy(d_a, h_a, n * sizeof(float), cudaMemcpyHostToDevice);
// ... kernel ...
cudaMemcpy(h_a, d_a, n * sizeof(float), cudaMemcpyDeviceToHost);
cudaFree(d_a);
```

### Unified Memory (simpler, may be slower)

```cuda
float *data;
cudaMallocManaged(&data, n * sizeof(float));  // accessible from CPU and GPU
// ... use data on both sides ...
cudaFree(data);
```

## Warp-Level Primitives (CUDA 9+)

```cuda
// Warp shuffle — exchange values within a 32-thread warp without shared mem
float val = __shfl_down_sync(0xFFFFFFFF, thread_val, offset);

// Warp-level reduction
for (int offset = 16; offset > 0; offset >>= 1)
    val += __shfl_down_sync(0xFFFFFFFF, val, offset);
```

## Occupancy and Performance Tips

- **Thread count**: multiples of 32 (warp size); aim for ≥ 128 threads/block.
- **Register pressure**: `--maxrregcount=N` limits registers per thread; more threads → higher occupancy.
- **Bank conflicts**: shared memory has 32 banks; access pattern `arr[threadIdx.x + 1]` per thread avoids conflicts.
- **Coalesced global reads**: threads in a warp should access consecutive addresses.
- **Stream overlap**: use `cudaStream_t` to pipeline kernel execution with memory transfers.

## Error Checking Pattern

```cuda
#define CUDA_CHECK(call) \
    do { \
        cudaError_t err = (call); \
        if (err != cudaSuccess) { \
            fprintf(stderr, "CUDA error %s:%d: %s\n", __FILE__, __LINE__, \
                    cudaGetErrorString(err)); \
            exit(1); \
        } \
    } while (0)

CUDA_CHECK(cudaMalloc(&d_a, n * sizeof(float)));
```

## Common Pitfalls

- Launching with 0 blocks or 0 threads is silently ignored (not an error).
- Missing `__syncthreads()` after shared-memory loads causes race conditions.
- Writing out-of-bounds without bounds check causes silent corruption or crash.
- Forgetting `cudaDeviceSynchronize()` before reading results back to host.
